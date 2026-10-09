#!/usr/bin/env python3
"""Host phase accounting and real owned-process cleanup through the safe router.

Font generation/mount operations are deterministic fixtures. These durations do
not measure Android synthesis, device mounts, or a complete phone reboot.
"""
from decimal import Decimal
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


class SafeSwitchTimingTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='safe-switch-timing-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.module = self.root / 'module'
        self.common = self.module / 'common'
        self.legacy = self.common / 'legacy_v14_4'
        self.legacy.mkdir(parents=True)
        (self.module / 'config').mkdir()
        (self.module / 'module.prop').write_text('id=LuoShu\n')
        for name in ('task_scope.sh', 'task_scope.py', 'runtime_paths.sh',
                     'runtime_paths_lock.py', 'background_task.sh',
                     'font_switch_lock.sh', 'font_next_transaction.sh',
                     'legacy_v14_4/font_switch_safe.sh', 'legacy_v14_4/payload_clone.sh',
                     'legacy_v14_4/hyperos_full_coverage.sh', 'hyperos_metrics_batch.py',
                     'coloros_metrics_batch.py', 'font_metrics_normalize.py',
                     'font_slot_coverage.py', 'font_inventory.py', 'font_inventory_scan.py',
                     'hyperos_physical_policy.py', 'hyperos_global.sh',
                     'util_functions.sh', 'rom_adapters.sh'):
            shutil.copyfile(ROOT / 'common' / name, self.common / name)
        (self.legacy / 'util_functions.sh').write_text('''
check_coloros() { IS_COLOROS=false; [ "${TEST_ROM:-generic}" != coloros ] || IS_COLOROS=true; }
check_hyperos() { IS_HYPEROS=false; [ "${TEST_ROM:-generic}" != hyperos ] || IS_HYPEROS=true; }
detect_font_family() { printf '%s\\n' "${1%.ttf}"; }
''')
        (self.legacy / 'font_check.sh').write_text('''
font_validate() {
    sleep .12
    [ "${TEST_VALIDATE_FAIL:-0}" != 1 ] || return 7
}
''')
        (self.legacy / 'font_coverage.py').write_text('# fixture validator identity\n')
        (self.legacy / 'rom_adapters.sh').write_text('''
apply_font_by_rom() {
    [ "${TEST_MAPPING_FAIL:-0}" != 1 ] || return 7
    if [ "${TEST_MAPPING_HOLD:-0}" = 1 ]; then
        "$TEST_PYTHON" "$TEST_ESCAPED_WORKER" "$TEST_ROOT"
        return $?
    fi
    sleep .18
    mkdir -p "$2/.luoshu-font-store"
    cp "$1" "$2/.luoshu-font-store/regular.font" || return 1
    cp "$1" "$2/Roboto-Regular.ttf"
}
''')
        for name in ('hyperos_stage_complete.sh', 'coloros_stage_complete.sh'):
            (self.common / name).write_text('''
sleep .14
[ "${TEST_COMPLETE_FAIL:-0}" != 1 ] || exit 7
''')
        (self.common / 'font_live_switch.sh').write_text('''
sleep .11
printf '{"status":"ok","data":{"liveApplied":false}}\\n'
''')
        self.public = self.root / 'public'
        (self.public / 'fonts').mkdir(parents=True)
        (self.public / 'fonts/Selected.ttf').write_bytes(b'new font fixture' * 300)
        self.live = self.module / '.luoshu-payload/system/fonts'
        self.live.mkdir(parents=True)
        self.old = self.live / 'Roboto-Regular.ttf'
        self.old.write_bytes(b'old active font fixture' * 300)
        self.original = self.old.read_bytes()
        (self.module / 'config/active_font.conf').write_text('Original\n')
        self.worker = self.root / 'generator.py'
        self.worker.write_text('''import json, os, signal, sys, time
from pathlib import Path
root = Path(sys.argv[1])
if os.fork() == 0:
    os.setsid()
    if os.fork() != 0: os._exit(0)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    (root / 'escaped.json').write_text(json.dumps({'pid': os.getpid(), 'proc': os.readlink('/proc/self')}))
    while True: time.sleep(.02)
signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
while True: time.sleep(.02)
''')
        self.env = dict(os.environ, MODDIR=str(self.module),
                        LUOSHU_PUBLIC_DIR=str(self.public), TEST_ROOT=str(self.root),
                        TEST_PYTHON=sys.executable, TEST_ESCAPED_WORKER=str(self.worker),
                        LUOSHU_TASK_SCOPE_PYTHON=sys.executable,
                        LUOSHU_RUNTIME_PATHS_PYTHON=sys.executable)
        for name in ('LUOSHU_TASK_SCOPE_PID', 'LUOSHU_TASK_SCOPE_PIDFILE',
                     'LUOSHU_TASK_SCOPE_TMPDIR', 'LUOSHU_TASK_SCOPE_TASK',
                     'LUOSHU_SAFE_SWITCH_SCOPED', 'LUOSHU_REAL_MODDIR',
                     'LUOSHU_SCOPE_ALLOW_HANDOFF', 'LUOSHU_SCOPE_HANDOFF'):
            self.env.pop(name, None)
        self.command = ['sh', str(self.legacy / 'font_switch_safe.sh'), 'action', 'switch', 'Selected']
        artifact_root = os.environ.get('LUOSHU_TIMING_TEST_ARTIFACT_DIR')
        if artifact_root:
            self.addCleanup(self.archive, Path(artifact_root) / self._testMethodName)

    def archive(self, destination):
        destination.mkdir(parents=True, exist_ok=True)
        state = self.module / '.luoshu-state'
        for name in ('logs', 'tasks'):
            if (state / name).exists():
                shutil.copytree(state / name, destination / name, dirs_exist_ok=True)

    def run_switch(self, **env):
        return subprocess.run(self.command, env=dict(self.env, **env),
                              capture_output=True, text=True, timeout=10)

    def timing(self):
        log = self.module / '.luoshu-state/logs/fontswitch.log'
        return [dict(field.split('=', 1) for field in line.split()[1:])
                for line in log.read_text().splitlines() if line.startswith('[SAFE-TIMING] ')]

    def assert_accounted(self, status='completed', result=0):
        rows = self.timing()
        totals = [row for row in rows if row['event'] == 'total']
        self.assertEqual(len(totals), 1, rows)
        total = totals[0]
        self.assertEqual(total['status'], status)
        self.assertEqual(int(total['result']), result)
        self.assertEqual({row['task'] for row in rows}, {total['task']})
        active = None
        ended = {}
        previous_uptime = Decimal(0)
        for row in rows:
            uptime = Decimal(row['uptime'])
            self.assertGreaterEqual(uptime, previous_uptime)
            previous_uptime = uptime
            if row['event'] == 'begin':
                self.assertIsNone(active, rows)
                active = row
            elif row['event'] == 'end':
                self.assertIsNotNone(active, rows)
                self.assertEqual(active['phase'], row['phase'])
                self.assertEqual(int(row['elapsedMs']), int((uptime - Decimal(active['uptime'])) * 1000))
                ended[row['phase']] = row
                active = None
        self.assertIsNone(active, rows)
        self.assertIn('initialization', ended)
        self.assertIn('worker_cleanup', ended)
        self.assertEqual(ended['worker_cleanup']['status'], 'finished')
        self.assertGreaterEqual(int(total['elapsedMs']), sum(int(row['elapsedMs']) for row in ended.values()))
        proofs = list((self.module / '.luoshu-state/tasks').glob('*.pid.cleanup.json'))
        proof = next(json.loads(path.read_text()) for path in proofs
                     if json.loads(path.read_text())['task'] == total['task'])
        self.assertTrue(proof['cleaned'], proof)
        self.assertEqual(proof['leftoverPids'], [])
        self.assertEqual(proof['cleanupErrors'], [])
        self.assertGreaterEqual(proof['durationSeconds'] * 1000 + 20, int(total['elapsedMs']))
        self.assertEqual(list((self.module / '.luoshu-state/tasks').glob('*.pid')), [])
        self.assertEqual(list((self.module / '.luoshu-state/tasks').glob('*.owner.json')), [])
        self.assertEqual(list((self.module / '.luoshu-state/tmp').glob('task-*')), [])
        self.assertFalse((self.module / '.font_switch.lock').exists())
        self.assertEqual(self.old.read_bytes(), self.original)
        return ended, proof

    def test_cold_switch_accounts_for_all_worker_phases_and_preserves_live_payload(self):
        result = self.run_switch()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        ended, _ = self.assert_accounted()
        self.assertEqual(set(ended), {'initialization', 'source_lookup_validation', 'prewarm_wait',
                         'lock_recovery', 'clone_payload', 'clear_text_payload', 'cache_restore',
                         'map_rom', 'mirror_targets', 'cache_store', 'verify_payload',
                         'prepare_next_payload', 'write_state', 'commit_transaction',
                         'live_mount', 'finalize', 'worker_cleanup'})
        self.assertGreaterEqual(int(ended['source_lookup_validation']['elapsedMs']), 100)
        self.assertGreaterEqual(int(ended['map_rom']['elapsedMs']), 160)
        self.assertGreaterEqual(int(ended['live_mount']['elapsedMs']), 90)
        pending = self.module / '.luoshu-payload-next/system/fonts/Roboto-Regular.ttf'
        self.assertEqual(pending.read_bytes(), (self.public / 'fonts/Selected.ttf').read_bytes())

    def test_warm_switch_accounts_for_cache_restore_without_mapping(self):
        self.assertEqual(self.run_switch().returncode, 0)
        log = self.module / '.luoshu-state/logs/fontswitch.log'
        log.write_text('')
        result = self.run_switch(TEST_MAPPING_FAIL='1')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        ended, _ = self.assert_accounted()
        self.assertIn('cache_restore', ended)
        self.assertNotIn('map_rom', ended)
        self.assertNotIn('cache_store', ended)

    def test_validation_failure_archives_failed_phase_and_cleanup(self):
        result = self.run_switch(TEST_VALIDATE_FAIL='1')
        self.assertNotEqual(result.returncode, 0)
        ended, _ = self.assert_accounted('failed', 1)
        self.assertEqual(ended['source_lookup_validation']['status'], 'failed')
        self.assertNotIn('lock_recovery', ended)
        self.assertFalse((self.module / '.luoshu-payload-next').exists())

    def test_mapping_failure_archives_failure_without_committing(self):
        result = self.run_switch(TEST_MAPPING_FAIL='1')
        self.assertNotEqual(result.returncode, 0)
        ended, _ = self.assert_accounted('failed', 1)
        self.assertEqual(ended['map_rom']['status'], 'failed')
        self.assertNotIn('prepare_next_payload', ended)
        self.assertFalse((self.module / '.luoshu-payload-next').exists())

    def test_rom_completion_is_measured_and_failure_never_commits(self):
        for rom in ('hyperos', 'coloros'):
            with self.subTest(rom=rom):
                log = self.module / '.luoshu-state/logs/fontswitch.log'
                if log.exists():
                    log.write_text('')
                result = self.run_switch(TEST_ROM=rom, TEST_COMPLETE_FAIL='1')
                self.assertNotEqual(result.returncode, 0)
                ended, _ = self.assert_accounted('failed', 1)
                self.assertEqual(ended['complete_' + rom]['status'], 'failed')
                self.assertGreaterEqual(int(ended['complete_' + rom]['elapsedMs']), 120)
                self.assertFalse((self.module / '.luoshu-payload-next').exists())

    @staticmethod
    def dispose(process):
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)

    def held_switch(self, timeout='8'):
        sentinel = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)',
                                     'luoshu-python', 'font-generator'])
        self.addCleanup(self.dispose, sentinel)
        process = subprocess.Popen(self.command,
            env=dict(self.env, TEST_MAPPING_HOLD='1', LUOSHU_SAFE_SWITCH_TIMEOUT=timeout),
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(self.dispose, process)
        deadline = time.monotonic() + 5
        while not (self.root / 'escaped.json').exists() and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertTrue((self.root / 'escaped.json').exists(), 'owned escaped generator never started')
        return process, sentinel

    def assert_escaped_reaped(self, sentinel):
        record = json.loads((self.root / 'escaped.json').read_text())
        self.assertFalse(Path('/proc', record['proc']).exists(), 'escaped generator was not reaped')
        self.assertIsNone(sentinel.poll(), 'unrelated font-tool process was signalled')
        self.assertFalse((self.module / '.luoshu-payload-next').exists())

    def test_timeout_archives_interruption_and_reaps_only_owned_escaped_generator(self):
        process, sentinel = self.held_switch(timeout='1')
        self.assertEqual(process.wait(timeout=8), 124)
        ended, proof = self.assert_accounted('interrupted', 143)
        self.assertEqual(ended['map_rom']['status'], 'interrupted')
        self.assertEqual(proof['reason'], 'timeout')
        self.assert_escaped_reaped(sentinel)

    def test_exact_cancel_archives_once_and_reaps_owned_escaped_generator(self):
        process, sentinel = self.held_switch()
        pidfile = next((self.module / '.luoshu-state/tasks').glob('safe-switch-*.pid'))
        owner = json.loads(Path(str(pidfile) + '.owner.json').read_text())
        wrong = subprocess.run([sys.executable, str(self.common / 'task_scope.py'), 'cancel',
                                str(pidfile), 'different-task'], env=self.env, capture_output=True, timeout=5)
        self.assertEqual(wrong.returncode, 3)
        self.assertIsNone(process.poll())
        cancel = subprocess.run([sys.executable, str(self.common / 'task_scope.py'), 'cancel',
                                 str(pidfile), owner['task']], env=self.env,
                                capture_output=True, text=True, timeout=8)
        self.assertEqual(cancel.returncode, 0, cancel.stdout + cancel.stderr)
        self.assertTrue(json.loads(cancel.stdout)['data']['cleaned'])
        self.assertEqual(process.wait(timeout=8), 143)
        ended, proof = self.assert_accounted('interrupted', 143)
        self.assertEqual(ended['map_rom']['status'], 'interrupted')
        self.assertEqual(proof['reason'], 'cancelled')
        self.assert_escaped_reaped(sentinel)

    def test_long_uptime_clock_does_not_overflow_absolute_milliseconds(self):
        source = (ROOT / 'common/legacy_v14_4/font_switch_safe.sh').read_text()
        start = source.index('safe_timing_clock() {')
        stop = source.index('\nsafe_timing_phase_end() {', start)
        # At 30 days, mksh's absolute milliseconds exceed its signed 32-bit
        # range. Read the real functions and use only a short seconds delta.
        command = source[start:stop] + '''
safe_timing_clock 2592000.09 || exit 1
safe_timing_elapsed 2591999 990
printf '%s\\n' "$SAFE_TIMING_ELAPSED_MS"
'''
        result = subprocess.run(['sh', '-c', command], capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout, '100\n')


if __name__ == '__main__':
    unittest.main()
