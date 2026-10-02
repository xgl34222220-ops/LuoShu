#!/usr/bin/env python3
"""Host-only selected-family snapshot, admission, validation and scope regression."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'common'))
import font_switch_input as switch
import task_scope


def wait_for(check, timeout=12):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(.025)
    raise AssertionError('bounded task did not finish')


class SwitchInputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.public = self.root / 'public'; self.fonts = self.public / 'fonts'; self.fonts.mkdir(parents=True)
        self.module = self.root / 'module'; (self.module / 'config').mkdir(parents=True)
        self.workspace = self.module / 'cache/tasks/token'; self.workspace.mkdir(parents=True)
        (self.workspace / '.luoshu-task-owner').write_text('token')
        self.font = self.fonts / 'Demo-Regular.ttf'
        self.font.write_bytes(b'\0\1\0\0' + b'A' * 5000)
        self.manager = self.root / 'manager.sh'
        self.manager.write_text('''#!/bin/sh
if [ "$2" = validate ]; then
    printf '%s\\n' '{"status":"ok","data":{"valid":true,"cached":false}}'
    exit 0
fi
printf '%s\\n' "$LUOSHU_PUBLIC_DIR" > "$CORE_MARKER"
printf '%s\\n' '{"status":"ok","data":{"font":"Demo"}}'
''')
        self.env = dict(os.environ, MODDIR=str(self.module), LUOSHU_PUBLIC_DIR=str(self.public),
                        LUOSHU_TASK_SCOPE='token', LUOSHU_TASK_WORK_DIR=str(self.workspace),
                        LUOSHU_SWITCH_TASK_ID='test-task', LUOSHU_FONT_MANAGER=str(self.manager),
                        CORE_MARKER=str(self.root / 'core-entered'))

    def snapshot(self, expected=''):
        return switch.make_snapshot(self.public, 'Demo', self.workspace, expected)

    def run_helper(self, action='run', family='Demo', fingerprint=''):
        return subprocess.run([sys.executable, str(ROOT / 'common/font_switch_input.py'),
                               action, family, fingerprint], env=self.env, text=True,
                              capture_output=True, timeout=10)

    def test_preflight_is_lightweight_with_explicit_identity(self):
        result = self.run_helper('preflight')
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        data = json.loads(result.stdout)['data']
        self.assertTrue(data['valid']); self.assertEqual('preflight-only', data['validation'])
        self.assertEqual(switch.fingerprint(switch.selection(self.public, 'Demo')), data['fingerprint'])
        self.assertFalse((self.root / 'core-entered').exists())
        self.assertFalse((self.workspace / 'font-input').exists())

    def test_only_family_copied_and_core_first_file_order_preserved(self):
        for name in ('Demo-Bold.ttf', 'Demo-Regular.otf', 'Demo-Light.TTF', 'Other.ttf'):
            (self.fonts / name).write_bytes(b'\0\1\0\0' + name.encode() * 1024)
        (self.fonts / 'Demo.conf').write_text('name=中文\\字体\nsupports_cjk=true\n')
        private, selected, hashes = self.snapshot()
        expected = ['Demo-Bold.ttf', 'Demo-Regular.ttf', 'Demo-Regular.otf', 'Demo-Light.TTF', 'Demo.conf']
        self.assertEqual(expected, [row['name'] for row in selected['files']])
        self.assertEqual(set(expected), {p.name for p in (private / 'fonts').iterdir()})
        self.assertEqual((self.fonts / 'Demo.conf').read_bytes(), (private / 'fonts/Demo.conf').read_bytes())
        switch.confirm_snapshot(self.public, private, selected, hashes)

    def test_family_detection_matches_current_and_frozen_utilities(self):
        names = ['Demo-Regular.ttf', 'Demo-Bold-Light.ttf', 'Demo-Light-Bold.ttf',
                 'Demo-ExtraBold.otf', '中文-半粗.TTF', 'Demo-Black-Italic.ttf', 'Demo--.ttc']
        for helper in ('common/util_functions_core.sh', 'common/legacy_v14_4/util_functions.sh'):
            output = subprocess.check_output(['sh', '-c', '. "$1"; shift; for name do detect_font_family "$name"; done',
                                              'test', str(ROOT / helper), *names], text=True)
            self.assertEqual([switch.family_of(name) for name in names], output.splitlines())

    def test_preflight_rejects_wrong_format_small_missing_and_bad_id(self):
        for value in (b'PK\3\4' + b'x' * 5000, b'\0\1\0\0'):
            self.font.write_bytes(value)
            with self.assertRaises(ValueError): switch.preflight(self.public, 'Demo')
        for family in ('../Demo', 'Demo\nstate=success', 'missing'):
            with self.assertRaises(ValueError): switch.preflight(self.public, family)

    def test_preflight_to_copy_replacement_rejected(self):
        expected = switch.preflight(self.public, 'Demo')['fingerprint']
        self.font.unlink(); self.font.write_bytes(b'\0\1\0\0' + b'B' * 5000)
        with self.assertRaises(ValueError): self.snapshot(expected)

    def test_copy_race_rejected(self):
        original_read = switch.checked_read
        def changing(*args, **kwargs):
            result = original_read(*args, **kwargs)
            self.font.write_bytes(b'\0\1\0\0' + b'B' * 5000)
            return result
        with mock.patch.object(switch, 'checked_read', side_effect=changing), self.assertRaises(ValueError):
            self.snapshot()

    def test_after_validation_source_delete_replace_mode_and_config_changes_rejected(self):
        for change in ('delete', 'replace', 'mode', 'config', 'add-weight'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as directory:
                work = Path(directory)
                private, selected, hashes = switch.make_snapshot(self.public, 'Demo', work)
                original = self.font.read_bytes()
                if change == 'delete': self.font.unlink()
                elif change == 'replace': self.font.write_bytes(b'\0\1\0\0' + b'B' * 5000)
                elif change == 'mode': self.font.chmod(0o600)
                elif change == 'config': (self.fonts / 'Demo.conf').write_text('name=changed')
                else: (self.fonts / 'Demo-Bold.ttf').write_bytes(original)
                with self.assertRaises((OSError, ValueError)):
                    switch.confirm_snapshot(self.public, private, selected, hashes)
                self.font.write_bytes(original); self.font.chmod(0o644)
                (self.fonts / 'Demo.conf').unlink(missing_ok=True)
                (self.fonts / 'Demo-Bold.ttf').unlink(missing_ok=True)

    def test_symlink_target_change_rejected_and_copy_is_regular(self):
        target = self.root / 'target.ttf'; target.write_bytes(self.font.read_bytes())
        self.font.unlink(); self.font.symlink_to(target)
        private, selected, hashes = self.snapshot()
        self.assertFalse((private / 'fonts' / self.font.name).is_symlink())
        other = self.root / 'other.ttf'; other.write_bytes(target.read_bytes())
        self.font.unlink(); self.font.symlink_to(other)
        with self.assertRaises(ValueError): switch.confirm_snapshot(self.public, private, selected, hashes)

    def test_config_content_and_private_snapshot_tampering_rejected(self):
        config = self.fonts / 'Demo.conf'; config.write_text('name=before')
        private, selected, hashes = self.snapshot()
        config.write_text('name=after!')
        with self.assertRaises(ValueError): switch.confirm_snapshot(self.public, private, selected, hashes)
        config.write_text('name=before')
        # Even when public metadata is recaptured, private changed bytes cannot pass.
        selected = switch.selection(self.public, 'Demo')
        copy = private / 'fonts' / self.font.name; copy.chmod(0o600); copy.write_bytes(b'changed')
        with self.assertRaises(ValueError): switch.confirm_snapshot(self.public, private, selected, hashes)

    def test_validation_and_core_share_private_bytes_and_emit_evidence(self):
        result = self.run_helper()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertEqual(str(self.workspace / 'font-input'), (self.root / 'core-entered').read_text().strip())
        events = [json.loads(line.split('] ',1)[1]) for line in result.stderr.splitlines()
                  if line.startswith('[font-switch-input] ')]
        self.assertEqual(['snapshot', 'full_validation', 'core_entry'], [e['event'] for e in events])
        self.assertFalse(events[1]['cached']); self.assertTrue(events[1]['valid'])
        self.assertTrue(events[2]['source_rechecked'])
        self.assertEqual(events[0]['snapshot_digest'], events[2]['snapshot_digest'])
        self.assertNotIn(str(self.public), result.stderr)

    def test_full_validation_failure_does_not_enter_core(self):
        self.manager.write_text('''#!/bin/sh
printf '%s\\n' '{"status":"ok","data":{"valid":false,"error":"覆盖不足"}}'
''')
        result = self.run_helper()
        self.assertEqual(1, result.returncode); self.assertIn('覆盖不足', result.stdout)
        self.assertFalse((self.root / 'core-entered').exists())

    def test_source_changed_during_full_validation_does_not_enter_core(self):
        self.manager.write_text('''#!/bin/sh
if [ "$2" = validate ]; then
    printf changed > "$ORIGINAL_FONT"
    printf '%s\\n' '{"status":"ok","data":{"valid":true,"cached":false}}'
else touch "$CORE_MARKER"; fi
''')
        self.env['ORIGINAL_FONT'] = str(self.font)
        result = self.run_helper()
        self.assertEqual(1, result.returncode); self.assertFalse((self.root / 'core-entered').exists())

    def test_explicit_full_and_empty_legacy_environment(self):
        self.manager.write_text('''#!/bin/sh
if [ "$2" = validate ]; then
    [ "$LUOSHU_VALIDATION_MODE" = full ] || exit 4
    [ -d "$LEGACY_FONTS_DIR" ] && [ -z "$(ls -A "$LEGACY_FONTS_DIR")" ] || exit 5
    [ "$MODDIR" = "$EXPECTED_MODULE" ] || exit 6
    printf '%s\\n' '{"status":"ok","data":{"valid":true,"cached":false}}'
else touch "$CORE_MARKER"; fi
''')
        self.env['EXPECTED_MODULE'] = str(self.module)
        self.assertEqual(0, self.run_helper().returncode)
        self.assertTrue((self.root / 'core-entered').exists())

    def test_missing_scope_and_wrong_marker_rejected(self):
        for key in ('LUOSHU_TASK_WORK_DIR', 'LUOSHU_TASK_SCOPE'):
            saved = self.env.pop(key)
            self.assertEqual(1, self.run_helper().returncode)
            self.env[key] = saved
        (self.workspace / '.luoshu-task-owner').write_text('other')
        self.assertEqual(1, self.run_helper().returncode)
        self.assertFalse((self.root / 'core-entered').exists())

    def test_default_restoration_needs_no_font_or_snapshot(self):
        self.env.pop('LUOSHU_TASK_SCOPE'); shutil.rmtree(self.fonts)
        result = self.run_helper(family='default')
        self.assertEqual(0, result.returncode)
        self.assertFalse((self.workspace / 'font-input').exists())

    def test_full_validation_timeout_and_cancel_reap_owned_descendants(self):
        # Exercise this new wrapper under the real finite task supervisor, not a
        # replacement scope or only the earlier generic orphan fixtures.
        for mode in ('timeout', 'cancel'):
            with self.subTest(mode=mode):
                leaf = self.root / ('leaf-' + mode)
                child = self.root / ('validator-' + mode + '.py')
                child.write_text('''import os,signal,time
from pathlib import Path
if os.fork() == 0:
 os.setsid()
 if os.fork() != 0: os._exit(0)
 signal.signal(signal.SIGTERM, signal.SIG_IGN)
 Path(os.environ['LEAF']).write_text(str(os.getpid()))
 while True: time.sleep(.05)
while True: time.sleep(.05)
''')
                self.manager.write_text('#!/bin/sh\nexec ' + sys.executable + ' ' + str(child) + '\n')
                pidfile = self.module / 'config' / (mode + '.pid')
                log = self.root / (mode + '.log')
                env = dict(self.env, LEAF=str(leaf), LUOSHU_TASK_TIMEOUT_SECONDS='2' if mode == 'timeout' else '20')
                command = [sys.executable, str(ROOT / 'common/task_scope.py'), 'launch', str(pidfile), mode, str(log), '--',
                           sys.executable, str(ROOT / 'common/font_switch_input.py'), 'run', 'Demo']
                result = subprocess.run(command, env=env, capture_output=True, timeout=10)
                self.assertEqual(0, result.returncode, result.stderr)
                leaf_pid = int(wait_for(lambda: leaf.read_text() if leaf.exists() else ''))
                if mode == 'cancel':
                    subprocess.run([sys.executable, str(ROOT / 'common/task_scope.py'), 'stop', str(pidfile), mode],
                                   env=env, check=True, timeout=12)
                wait_for(lambda: not Path(str(pidfile) + '.identity').exists())
                self.assertFalse(Path('/proc', str(leaf_pid)).exists(), 'owned validator child/zombie survived')
                self.assertFalse((self.root / 'core-entered').exists())
                self.assertEqual(['token'], [p.name for p in (self.module / 'cache/tasks').iterdir()])


if __name__ == '__main__':
    unittest.main()
