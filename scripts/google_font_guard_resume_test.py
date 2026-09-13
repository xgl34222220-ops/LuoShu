#!/usr/bin/env python3
"""Run the real guard service with controlled Android command/bridge fixtures.

Only lifecycle is simulated: these are not device, namespace or rendering tests.
"""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


class GuardResumeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='luoshu-guard-resume-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.module = self.root / 'module'
        (self.module / 'common').mkdir(parents=True)
        (self.module / 'config').mkdir()
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.active = self.module / 'config/active_font.conf'
        self.active.write_text('custom\n')
        shutil.copyfile(ROOT / 'common/font_switch_lock.sh', self.module / 'common/font_switch_lock.sh')
        self.command('getprop', 'echo 1\n')
        (self.module / 'common/google_font_provider_bridge.sh').write_text('''
case "$1" in
 fingerprint) echo same-font-and-namespace; echo fingerprint >> "$TEST_ROOT/probes" ;;
 apply) echo applied >> "$TEST_ROOT/applied"; exit "${TEST_APPLY_RC:-0}" ;;
 restore) echo restored >> "$TEST_ROOT/restored"; exit "${TEST_RESTORE_RC:-0}" ;;
esac
''')
        self.env = dict(os.environ, MODDIR=str(self.module), TEST_ROOT=str(self.root),
                        PATH=f"{self.bin}:{os.environ['PATH']}",
                        LUOSHU_GOOGLE_FONT_RETRIES='1', LUOSHU_GOOGLE_FONT_WATCH_INTERVAL='30',
                        LUOSHU_GOOGLE_FONT_WATCH_CYCLES='4')

    def command(self, name, body):
        path = self.bin / name
        path.write_text('#!/bin/sh\n' + body)
        path.chmod(0o755)

    def rows(self, name):
        path = self.root / name
        return path.read_text().splitlines() if path.exists() else []

    def run_guard(self, action=':', **env):
        self.command('sleep', '''
count=$(cat "$TEST_ROOT/ticks" 2>/dev/null || echo 0)
count=$((count + 1))
echo "$count" > "$TEST_ROOT/ticks"
''' + action + '\n')
        return subprocess.run(['sh', str(ROOT / 'common/google_font_provider_service.sh')],
                              env=dict(self.env, **env), text=True, capture_output=True, timeout=10)

    def test_default_at_boot_can_activate_without_restarting_guard(self):
        self.active.write_text('default\n')
        result = self.run_guard('if [ "$count" = 2 ]; then echo custom > "$MODDIR/config/active_font.conf"; fi')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.rows('restored'), ['restored'])
        self.assertEqual(self.rows('applied'), ['applied'])

    def test_default_then_same_selection_is_repaired_even_with_unchanged_fingerprint(self):
        result = self.run_guard('''
case "$count" in
 1) echo default > "$MODDIR/config/active_font.conf" ;;
 2) echo custom > "$MODDIR/config/active_font.conf" ;;
esac
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.rows('restored'), ['restored'])
        self.assertEqual(self.rows('applied'), ['applied', 'applied'])

    def test_missing_selection_at_boot_remains_recoverable(self):
        self.active.unlink()
        result = self.run_guard('if [ "$count" = 1 ]; then echo custom > "$MODDIR/config/active_font.conf"; fi')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.rows('applied'), ['applied'])

    def test_idle_default_restores_once_without_fingerprints_or_rebuilds(self):
        self.active.write_text('default\n')
        result = self.run_guard()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.rows('restored'), ['restored'])
        self.assertEqual(self.rows('probes'), [])
        self.assertEqual(self.rows('applied'), [])

    def test_disable_still_restores_and_exits(self):
        result = self.run_guard('touch "$MODDIR/disable"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.rows('restored'), ['restored'])
        self.assertEqual(self.rows('applied'), ['applied'])
        self.assertFalse((self.module / '.google-font-provider.lock').exists())

    def test_restore_failure_remains_visible_and_bounded(self):
        self.active.write_text('default\n')
        result = self.run_guard(TEST_RESTORE_RC='1')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.rows('restored'), ['restored'] * 3)
        self.assertFalse((self.module / '.google-font-provider.lock').exists())

    def observer(self, body):
        binary = self.module / 'common/python/bin/luoshu-python'
        binary.parent.mkdir(parents=True, exist_ok=True)
        binary.write_text('#!/bin/sh\n' + body)
        binary.chmod(0o755)
        (self.module / 'common/google_font_watch_wait.py').write_text('# fixture entry\n')

    def test_event_wake_does_not_fall_back_to_blind_sleep_or_rebuild_unchanged_font(self):
        self.observer('echo event >> "$TEST_ROOT/events"\nexit 0\n')
        result = self.run_guard()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.rows('events'), ['event'] * 4)
        self.assertEqual(self.rows('applied'), ['applied'])
        self.assertEqual(self.rows('ticks'), [])

    def test_unavailable_observer_uses_bounded_sleep(self):
        self.observer('echo failed >> "$TEST_ROOT/events"\nexit 3\n')
        result = self.run_guard()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.rows('events'), ['failed'] * 4)
        self.assertEqual(self.rows('ticks'), ['4'])
        self.assertEqual(self.rows('applied'), ['applied'])

    def test_early_events_do_not_consume_full_failure_backoff_intervals(self):
        self.observer('exit 0\n')
        self.command('date', 'echo 1000\n')
        result = self.run_guard(TEST_APPLY_RC='1', LUOSHU_GOOGLE_FONT_WATCH_CYCLES='15')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.rows('applied'), ['applied'])

    def test_observer_timeouts_keep_existing_failure_backoff(self):
        self.observer('exit 2\n')
        result = self.run_guard(TEST_APPLY_RC='1', LUOSHU_GOOGLE_FONT_WATCH_CYCLES='11')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.rows('applied'), ['applied', 'applied'])

    def test_term_cancels_idle_wait_and_releases_lifetime_lock(self):
        self.command('sleep', 'echo $$ > "$TEST_ROOT/sleeper"\nexec /bin/sleep 30\n')
        process = subprocess.Popen(['sh', str(ROOT / 'common/google_font_provider_service.sh')],
                                   env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 5
            while not (self.root / 'sleeper').exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue((self.root / 'sleeper').exists())
            child = int((self.root / 'sleeper').read_text())
            process.terminate()
            process.communicate(timeout=3)
            self.assertEqual(process.returncode, 143)
            with self.assertRaises(ProcessLookupError):
                os.kill(child, 0)
            self.assertFalse((self.module / '.google-font-provider.lock').exists())
        finally:
            if process.poll() is None:
                process.kill()
                # A failing pre-fix guard leaves a real /bin/sleep holding the pipe.
                if (self.root / 'sleeper').exists():
                    try:
                        os.kill(int((self.root / 'sleeper').read_text()), 9)
                    except ProcessLookupError:
                        pass
                process.communicate(timeout=3)


if __name__ == '__main__':
    unittest.main(verbosity=2)
