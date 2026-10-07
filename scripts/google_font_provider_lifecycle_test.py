#!/usr/bin/env python3
"""One-shot provider lifecycle using the actual child-tree supervisor.

Android font/mount behavior remains covered by the bridge and patch suites.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


def install_support(module):
    common = module / 'common'
    common.mkdir(parents=True, exist_ok=True)
    for name in ('task_scope.sh', 'task_scope.py', 'runtime_paths.sh', 'runtime_paths_lock.py', 'font_switch_lock.sh'):
        shutil.copyfile(ROOT / 'common' / name, common / name)


class ProviderLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='provider-one-shot-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.module = self.root / 'module'
        install_support(self.module)
        (self.module / 'config').mkdir()
        self.active = self.module / 'config/active_font.conf'
        self.active.write_text('custom\n')
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.command('getprop', 'echo 1\n')
        self.command('sleep', 'echo sleep >> "$TEST_ROOT/sleeps"\n')
        self.bridge('''
case "$1" in
 apply) echo applied >> "$TEST_ROOT/applied"; exit "${TEST_APPLY_RC:-0}" ;;
 restore) echo restored >> "$TEST_ROOT/restored"; exit "${TEST_RESTORE_RC:-0}" ;;
 refresh) echo refreshed >> "$TEST_ROOT/refreshed"; exit "${TEST_REFRESH_RC:-0}" ;;
 fingerprint) echo unexpected >> "$TEST_ROOT/fingerprints" ;;
esac
''')
        self.env = dict(os.environ, MODDIR=str(self.module), TEST_ROOT=str(self.root),
                        PATH=f'{self.bin}:{os.environ["PATH"]}',
                        LUOSHU_TASK_SCOPE_PYTHON=sys.executable,
                        LUOSHU_RUNTIME_PATHS_PYTHON=sys.executable)

    def command(self, name, body):
        path = self.bin / name
        path.write_text('#!/bin/sh\n' + body)
        path.chmod(0o755)

    def bridge(self, body):
        (self.module / 'common/google_font_provider_bridge.sh').write_text(body)

    def rows(self, name):
        path = self.root / name
        return path.read_text().splitlines() if path.exists() else []

    def run_service(self, mode='boot', **env):
        result = subprocess.run(['sh', str(ROOT / 'common/google_font_provider_service.sh'), mode],
                                env=dict(self.env, **env), text=True, capture_output=True, timeout=8)
        self.assert_clean()
        return result

    def assert_clean(self):
        tasks = self.module / '.luoshu-state/tasks'
        self.assertFalse((tasks / 'google-font-provider.lock').exists())
        self.assertFalse((tasks / 'font-provider-service.pid').exists())
        for suffix in ('.task', '.start', '.boot', '.owner.json', '.ready'):
            self.assertFalse((tasks / ('font-provider-service.pid' + suffix)).exists())
        proof = json.loads((tasks / 'font-provider-service.pid.cleanup.json').read_text())
        self.assertTrue(proof['cleaned'], proof)
        self.assertEqual(proof['leftoverPids'], [])
        return proof

    def theme(self):
        (self.module / 'common/hyperos_theme_font_bridge.sh').write_text('''
case "$1" in
 apply) echo theme-applied >> "$TEST_ROOT/theme"; exit "${TEST_THEME_RC:-0}" ;;
 restore) echo theme-restored >> "$TEST_ROOT/theme"; exit "${TEST_THEME_RC:-0}" ;;
esac
''')

    def test_success_applies_once_and_exits_without_idle_watch_or_retry(self):
        result = self.run_service(LUOSHU_GOOGLE_FONT_WATCH_CYCLES='-1',
                                  LUOSHU_GOOGLE_FONT_RETRIES='999')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.rows('applied'), ['applied'])
        self.assertEqual(self.rows('sleeps'), [])
        self.assertEqual(self.rows('fingerprints'), [])

    def test_no_downloads_and_errors_exit_after_one_attempt(self):
        for rc, expected in (('2', 0), ('1', 1), ('137', 1)):
            with self.subTest(rc=rc):
                (self.root / 'applied').unlink(missing_ok=True)
                result = self.run_service(TEST_APPLY_RC=rc)
                self.assertEqual(result.returncode, expected, result.stderr)
                self.assertEqual(self.rows('applied'), ['applied'])
                self.assertEqual(self.rows('sleeps'), [])

    def test_theme_runs_once_even_when_google_has_no_download(self):
        self.theme()
        result = self.run_service(TEST_APPLY_RC='2')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.rows('theme'), ['theme-applied'])

    def test_theme_error_is_visible_and_does_not_start_background_retry(self):
        self.theme()
        result = self.run_service(TEST_THEME_RC='1')
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(self.rows('theme'), ['theme-applied'])
        self.assertEqual(self.rows('sleeps'), [])

    def fallback(self):
        (self.module / 'common/google_font_fallback.sh').write_text('''
printf '%s\\n' "$*" >> "$TEST_ROOT/fallback"
printf '%s\\n' '{"status":"unchanged","message":"owned one-shot fixture"}'
exit "${TEST_FALLBACK_RC:-0}"
''')

    def test_owned_fallback_reconciliation_is_one_bounded_pass_before_mounts(self):
        self.fallback()
        result = self.run_service('reconcile')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.rows('fallback'), ['reconcile-owned --json'])
        self.assertEqual(self.rows('applied'), ['applied'])
        self.assertEqual(self.rows('sleeps'), [])
        log = self.module / '.luoshu-state/logs/google-font-compatibility.log'
        self.assertIn('owned one-shot fixture', log.read_text())

    def test_owned_fallback_failure_is_reported_without_skipping_other_adapters_or_retrying(self):
        self.fallback()
        result = self.run_service(TEST_FALLBACK_RC='1')
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(self.rows('fallback'), ['reconcile-owned --json'])
        self.assertEqual(self.rows('applied'), ['applied'])
        self.assertEqual(self.rows('sleeps'), [])

    def test_default_font_does_not_reapply_component_compatibility(self):
        self.fallback()
        self.active.write_text('default\n')
        result = self.run_service()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.rows('fallback'), [])
        self.assertEqual(self.rows('restored'), ['restored'])

    def test_default_disable_remove_restore_both_adapters_then_exit(self):
        self.theme()
        for stop in ('default', 'disable', 'remove'):
            with self.subTest(stop=stop):
                self.active.write_text('default\n' if stop == 'default' else 'custom\n')
                for marker in ('disable', 'remove'):
                    (self.module / marker).unlink(missing_ok=True)
                if stop != 'default':
                    (self.module / stop).touch()
                for name in ('restored', 'theme'):
                    (self.root / name).unlink(missing_ok=True)
                result = self.run_service()
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.rows('restored'), ['restored'])
                self.assertEqual(self.rows('theme'), ['theme-restored'])
                self.assertEqual(self.rows('applied'), [])

    def test_restore_failure_preserves_recovery_journal_and_exits(self):
        self.active.write_text('default\n')
        journal = self.module / 'config/google-font-provider-namespaces.conf'
        journal.write_text('owned mount to recover\n')
        result = self.run_service(TEST_RESTORE_RC='1')
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(self.rows('restored'), ['restored'])
        self.assertEqual(journal.read_text(), 'owned mount to recover\n')
        self.assertEqual(self.rows('sleeps'), [])

    def test_existing_refresh_queue_gets_one_pass_and_no_waiter(self):
        queue = self.module / 'config/google-font-refresh-pending.conf'
        queue.write_text('foreground consumer recovery record\n')
        result = self.run_service('reconcile')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.rows('refreshed'), ['refreshed'])
        self.assertTrue(queue.exists())
        self.assertEqual(self.rows('sleeps'), [])

    def test_explicit_reconcile_skips_boot_readiness_wait(self):
        self.command('getprop', 'echo 0\n')
        result = self.run_service('reconcile')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.rows('applied'), ['applied'])
        self.assertEqual(self.rows('sleeps'), [])

    def test_boot_readiness_wait_is_bounded_and_never_starts_idle_watch(self):
        self.command('getprop', 'echo 0\n')
        result = self.run_service(LUOSHU_GOOGLE_FONT_BOOT_WAIT_SECONDS='3')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.rows('sleeps'), ['sleep'] * 3)
        self.assertEqual(self.rows('applied'), [])

    def worker_fixture(self, result):
        self.bridge('''
case "$1" in
 apply)
   /bin/sleep 30 &
   echo "$!" > "$TEST_ROOT/child"
   echo applied >> "$TEST_ROOT/applied"
''' + result + '''
   ;;
esac
''')

    def assert_child_gone(self):
        pid = int((self.root / 'child').read_text())
        with self.assertRaises(ProcessLookupError):
            os.kill(pid, 0)

    def test_success_and_error_reap_leftover_worker_and_leave_unrelated_process_alive(self):
        unrelated = subprocess.Popen(['/bin/sleep', '30'])
        self.addCleanup(lambda: unrelated.wait(timeout=3))
        self.addCleanup(unrelated.terminate)
        for code in (0, 1):
            with self.subTest(code=code):
                self.worker_fixture(f'   exit {code}\n')
                result = self.run_service()
                self.assertEqual(result.returncode, code, result.stderr)
                self.assert_child_gone()
                self.assertIsNone(unrelated.poll())

    def test_timeout_reaps_active_worker_and_releases_lock(self):
        self.worker_fixture('   wait\n')
        result = self.run_service(LUOSHU_GOOGLE_FONT_TASK_TIMEOUT='0.25')
        self.assertEqual(result.returncode, 124, result.stderr)
        self.assertEqual(self.assert_clean()['reason'], 'timeout')
        self.assert_child_gone()

    def test_cancel_reaps_active_worker_and_releases_lock(self):
        self.worker_fixture('   wait\n')
        process = subprocess.Popen(['sh', str(ROOT / 'common/google_font_provider_service.sh'), 'reconcile'],
                                   env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 5
            while not (self.root / 'child').exists() and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertTrue((self.root / 'child').exists())
            process.terminate()
            _out, err = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 143, err)
            self.assert_clean()
            self.assert_child_gone()
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)


class DirectBridgeLifecycleTest(unittest.TestCase):
    command = ProviderLifecycleTest.command
    bridge = ProviderLifecycleTest.bridge
    def setUp(self):
        ProviderLifecycleTest.setUp(self)
        shutil.copyfile(ROOT / 'common/google_font_provider_bridge.sh',
                        self.module / 'common/google_font_provider_bridge.sh')
        (self.module / 'common/google_font_provider_patch.py').write_text('# lifecycle fixture\n')
        target = self.root / 'downloaded-font'
        target.write_bytes(b'font-lifecycle-fixture' * 128)
        sources = self.module / 'config/device-font-sources'
        sources.mkdir()
        shutil.copyfile(target, sources / 'LuoShu-400.ttf')
        python = self.root / 'python-worker'
        python.write_text('''#!/bin/sh
shift
case "$1" in
 --inspect-targets)
   /bin/sleep 30 &
   echo "$!" > "$TEST_ROOT/direct-child"
   [ "${TEST_WORKER_WAIT:-0}" != 1 ] || wait
   [ "${TEST_WORKER_ERROR:-0}" != 1 ] || exit 1
   while IFS= read -r target; do printf '%s\\t400\\n' "$target"; done < "$2"
   ;;
 *)
   while [ "$#" -gt 0 ]; do
     case "$1" in --target) target="$2"; shift;; --output) output="$2"; shift;; esac
     shift
   done
   cp "$target" "$output"
   echo '{"status":"ok"}'
   ;;
esac
''')
        python.chmod(0o755)
        self.env.update(LUOSHU_GOOGLE_FONT_PYTHON=str(python),
                        LUOSHU_GOOGLE_FONT_TARGETS=str(target))

    def direct(self, **env):
        return subprocess.run(['sh', str(self.module / 'common/google_font_provider_bridge.sh'), 'prepare'],
                              env=dict(self.env, **env), capture_output=True, text=True, timeout=8)

    def assert_direct_clean(self):
        tasks = self.module / '.luoshu-state/tasks'
        self.assertEqual(list(tasks.glob('*.pid')), [])
        self.assertFalse((tasks / 'google-font-provider-bridge.lock').exists())
        self.assertFalse((tasks / 'google-font-provider.lock').exists())
        proofs = list(tasks.glob('request-font-provider-*.pid.cleanup.json'))
        self.assertTrue(proofs)
        for path in proofs:
            proof = json.loads(path.read_text())
            self.assertTrue(proof['cleaned'], proof)
            self.assertEqual(proof['leftoverPids'], [])
        with self.assertRaises(ProcessLookupError):
            os.kill(int((self.root / 'direct-child').read_text()), 0)
        cache = self.module / '.luoshu-state/cache/google-font-provider'
        self.assertEqual(list(cache.glob('.*.*')), [])
        self.assertEqual(list(cache.glob('*.tmp.*')), [])

    def test_direct_bridge_success_and_error_reap_background_python_descendants(self):
        for error in ('0', '1'):
            with self.subTest(error=error):
                result = self.direct(TEST_WORKER_ERROR=error)
                self.assertEqual(result.returncode, int(error), result.stderr)
                self.assert_direct_clean()
                inspected = self.module / '.luoshu-state/cache/google-font-provider/inspected-targets-v1.conf'
                inspected.unlink(missing_ok=True)

    def test_direct_bridge_timeout_reaps_python_and_cleans_transaction_files(self):
        result = self.direct(TEST_WORKER_WAIT='1', LUOSHU_GOOGLE_FONT_TASK_TIMEOUT='0.25')
        self.assertEqual(result.returncode, 124, result.stderr)
        self.assert_direct_clean()

    def test_direct_bridge_cancel_reaps_python_and_cleans_transaction_files(self):
        process = subprocess.Popen(['sh', str(self.module / 'common/google_font_provider_bridge.sh'), 'prepare'],
                                   env=dict(self.env, TEST_WORKER_WAIT='1'),
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 5
            while not (self.root / 'direct-child').exists() and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertTrue((self.root / 'direct-child').exists())
            process.terminate()
            _out, error = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 143, error)
            self.assert_direct_clean()
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)


class NamespaceStageLifecycleTest(unittest.TestCase):
    command = ProviderLifecycleTest.command
    bridge = ProviderLifecycleTest.bridge

    def setUp(self):
        ProviderLifecycleTest.setUp(self)
        self.source = self.root / 'source.ttf'
        self.source.write_bytes(b'source' * 300)
        self.target = self.root / 'target.ttf'
        self.target.write_bytes(b'target' * 300)
        self.stage = self.root / 'namespace-stage'
        self.stage.mkdir()
        (self.stage / 'unrelated.keep').write_text('preserve unrelated data')
        self.command('nsenter', '''while [ "$1" != -- ]; do shift; done
shift
ns_shell="$1"; code="$3"
shift 4
source="$1"
shift 2
# Fixture boundary: PID 1's root is outside this host container. Preserve the
# helper's argument shape, modeling its readable proc-root view by this source.
exec "$ns_shell" -c "$code" sh "$source" "$source" "$@"
''')
        self.command('mount', 'echo fixture-bind-refused >&2\nexit 1\n')
        self.command('cat', '''if [ "$1" = "$TEST_STAGE_SOURCE" ]; then
 echo copying > "$TEST_ROOT/staging-started"
 exec /bin/sleep 30
fi
exec /bin/cat "$@"
''')

    def test_cancel_and_timeout_unlink_only_the_owned_namespace_stage(self):
        for mode in ('cancel', 'timeout'):
            with self.subTest(mode=mode):
                marker = self.root / 'staging-started'
                marker.unlink(missing_ok=True)
                script = '. "$1"; _gfp_mount_in_pid 1 "$2" "$3"'
                command = ['sh', str(self.module / 'common/task_scope.sh'), 'run',
                           '--pid-file', str(self.module / '.luoshu-state/tasks' / ('stage-' + mode + '.pid')),
                           '--task', 'provider-stage-' + mode, '--timeout', '2' if mode == 'timeout' else '10', '--',
                           'sh', '-c', script, 'sh', str(ROOT / 'common/google_font_provider_bridge.sh'),
                           str(self.source), str(self.target)]
                process = subprocess.Popen(command, env=dict(self.env, LUOSHU_GOOGLE_FONT_STAGE_DIR=str(self.stage),
                                           LUOSHU_GOOGLE_FONT_NS_SHELL='/bin/sh', TEST_STAGE_SOURCE=str(self.source)),
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                try:
                    deadline = time.monotonic() + 5
                    while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
                        time.sleep(.01)
                    self.assertTrue(marker.exists(), 'namespace helper did not reach its staging write')
                    self.assertEqual(len(list(self.stage.glob('.luoshu-provider-*.ttf'))), 1)
                    if mode == 'cancel':
                        process.terminate()
                    _out, error = process.communicate(timeout=5)
                    self.assertEqual(process.returncode, 143 if mode == 'cancel' else 124, error)
                    self.assertEqual(list(self.stage.glob('.luoshu-provider-*.ttf')), [])
                    self.assertEqual((self.stage / 'unrelated.keep').read_text(), 'preserve unrelated data')
                finally:
                    if process.poll() is None:
                        process.kill()
                    process.communicate(timeout=5)


if __name__ == '__main__':
    unittest.main(verbosity=2)
