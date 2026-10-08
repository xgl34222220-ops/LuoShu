#!/usr/bin/env python3
"""A finished reconciliation has no watcher; a later explicit call still repairs."""
import unittest
import json
import os
from pathlib import Path
import subprocess
import tempfile
import google_font_provider_lifecycle_test as fixtures


class ExplicitReconcileTest(unittest.TestCase):
    setUp = fixtures.ProviderLifecycleTest.setUp
    command = fixtures.ProviderLifecycleTest.command
    bridge = fixtures.ProviderLifecycleTest.bridge
    rows = fixtures.ProviderLifecycleTest.rows
    run_service = fixtures.ProviderLifecycleTest.run_service
    assert_clean = fixtures.ProviderLifecycleTest.assert_clean
    def test_later_explicit_apply_handles_new_selection_after_default_pass(self):
        self.active.write_text('default\n')
        first = self.run_service('reconcile')
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(self.rows('restored'), ['restored'])
        self.assertEqual(self.rows('applied'), [])
        self.active.write_text('custom\n')
        second = self.run_service('reconcile')
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(self.rows('applied'), ['applied'])
        self.assertEqual(self.rows('sleeps'), [])

    def test_same_selection_can_be_reconciled_again_without_a_resident_service(self):
        self.assertEqual(self.run_service('reconcile').returncode, 0)
        self.assertEqual(self.run_service('reconcile').returncode, 0)
        self.assertEqual(self.rows('applied'), ['applied', 'applied'])
        self.assertEqual(self.rows('fingerprints'), [])


class DisabledModuleFallbackRequestTest(unittest.TestCase):
    command = fixtures.ProviderLifecycleTest.command

    def request_env(self, module, uid):
        # The host may be unprivileged; model only the wrapper's id -u boundary.
        self.bin = module / 'bin'
        self.bin.mkdir()
        self.command('id', '[ "$#" = 1 ] && [ "$1" = -u ] || exit 2\n'
                     f"printf '{uid}\\n'\n")
        return dict(os.environ, MODDIR=str(module),
                    LUOSHU_TASK_SCOPE_PID=str(os.getpid()),
                    PATH=f'{self.bin}:{os.environ["PATH"]}')

    def test_disabled_or_removing_module_rejects_writes_before_initialization(self):
        source = Path(__file__).resolve().parents[1] / 'common/google_font_fallback.sh'
        for marker in ('disable', 'remove'):
            for shape in ('file', 'directory', 'dangling-symlink'):
                for action in ('enable', 'reapply-owned', 'reconcile-owned'):
                    with self.subTest(marker=marker, shape=shape, action=action), tempfile.TemporaryDirectory() as tmp:
                        module = Path(tmp)
                        common = module / 'common'
                        common.mkdir()
                        bridge = common / source.name
                        bridge.write_bytes(source.read_bytes())
                        (common / 'runtime_paths.sh').write_text(
                            'luoshu_runtime_paths_init() { touch "$MODDIR/initialized"; }\n')
                        launcher = common / 'python/bin/luoshu-python'
                        launcher.parent.mkdir(parents=True)
                        launcher.write_text('#!/bin/sh\ntouch "$MODDIR/executed"\nprintf \'{"status":"ok"}\\n\'\n')
                        launcher.chmod(0o700)
                        flag = module / marker
                        if shape == 'file': flag.touch()
                        elif shape == 'directory': flag.mkdir()
                        else: flag.symlink_to(module / 'missing-marker-target')
                        env = dict(os.environ, MODDIR=str(module), LUOSHU_TASK_SCOPE_PID=str(os.getpid()))
                        result = subprocess.run(['sh', str(bridge), action], env=env, text=True,
                                                capture_output=True, timeout=5)
                        self.assertNotEqual(result.returncode, 0, result)
                        self.assertEqual(json.loads(result.stdout)['status'], 'error')
                        self.assertFalse((module / 'initialized').exists(), result)
                        self.assertFalse((module / 'executed').exists(), result)

    def test_disabled_module_keeps_explicit_restore_available(self):
        source = Path(__file__).resolve().parents[1] / 'common/google_font_fallback.sh'
        for marker, action in ((marker, action) for marker in ('disable', 'remove')
                               for action in ('restore', 'restore-owned')):
            with self.subTest(marker=marker, action=action), tempfile.TemporaryDirectory() as tmp:
                module = Path(tmp)
                common = module / 'common'
                common.mkdir()
                bridge = common / source.name
                bridge.write_bytes(source.read_bytes())
                (module / marker).touch()
                launcher = common / 'python/bin/luoshu-python'
                launcher.parent.mkdir(parents=True)
                launcher.write_text('#!/bin/sh\nprintf \'{"status":"ok","action":"%s"}\\n\' "$2"\n')
                launcher.chmod(0o700)
                result = subprocess.run(['sh', str(bridge), action],
                    env=self.request_env(module, uid=0),
                    text=True, capture_output=True, timeout=5)
                self.assertEqual(result.returncode, 0, result)
                self.assertEqual(json.loads(result.stdout)['action'], action)

    def test_non_root_fixture_denies_restore_before_launcher_or_component_writes(self):
        source = Path(__file__).resolve().parents[1] / 'common/google_font_fallback.sh'
        for marker in ('disable', 'remove'):
            for action in ('restore', 'restore-owned'):
                with self.subTest(marker=marker, action=action), tempfile.TemporaryDirectory() as tmp:
                    module = Path(tmp)
                    common = module / 'common'
                    common.mkdir()
                    bridge = common / source.name
                    bridge.write_bytes(source.read_bytes())
                    (module / marker).touch()
                    # Runtime initialization precedes the permission check; this
                    # fixture makes no claim about all initialization writes.
                    (common / 'runtime_paths.sh').write_text(
                        'luoshu_runtime_paths_init() { return 0; }\n')
                    journal = module / 'original-undo.json'
                    original = b'{"original":0,"fixture":"preserve"}\n'
                    journal.write_bytes(original)
                    launcher = common / 'python/bin/luoshu-python'
                    launcher.parent.mkdir(parents=True)
                    launcher.write_text('#!/bin/sh\ntouch "$MODDIR/executed"\n'
                                        'pm disable fixture-component\n')
                    launcher.chmod(0o700)
                    env = self.request_env(module, uid=1001)
                    self.command('pm', 'touch "$MODDIR/component-write"\n')
                    result = subprocess.run(['sh', str(bridge), action], env=env,
                                            text=True, capture_output=True, timeout=5)
                    self.assertEqual(result.returncode, 1, result)
                    response = json.loads(result.stdout)
                    self.assertEqual(response['status'], 'error')
                    self.assertIn('Root', response['message'])
                    self.assertFalse((module / 'executed').exists(), result)
                    self.assertFalse((module / 'component-write').exists(), result)
                    self.assertEqual(journal.read_bytes(), original)


if __name__ == '__main__':
    unittest.main(verbosity=2)
