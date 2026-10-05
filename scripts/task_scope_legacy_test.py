#!/usr/bin/env python3
"""Legacy migration ownership regressions with no real process signaling.

Usage: python3 scripts/task_scope_legacy_test.py [repository_or_package_root]
All registrations are temporary; /proc enumeration, identities, command lines,
tree discovery, and signals are mocked. No old module or user record is read.
"""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import signal
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(sys.argv.pop(1)).resolve() if len(sys.argv) > 1 and not sys.argv[1].startswith('-') else Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('legacy_scope_under_test', ROOT / 'common/task_scope.py')
SCOPE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SCOPE)
REAL_ITERDIR = Path.iterdir
REAL_READ_BYTES = Path.read_bytes
OLD_BOOT = '00000000-0000-4000-8000-000000000001'
if OLD_BOOT == SCOPE.BOOT:
    OLD_BOOT = '00000000-0000-4000-8000-000000000002'


class LegacyOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='luoshu-legacy-cancel-test-')
        self.addCleanup(self.temporary.cleanup)
        self.module = Path(self.temporary.name)
        self.pidfile = self.module / 'config/mix_worker.pid'
        self.record = dict(procPid=4000, pid=4000, parent=1, start='200', state='S', boot=SCOPE.BOOT, namespace=SCOPE.SELF_NS)
        self.command = ['sh', str(self.module / 'common/font_mix.sh'), 'worker', 'old-task']
        self.live = True
        self.signals = []

    def register(self, *, text='4000\n', boot=SCOPE.BOOT, start=None, task='old-task', singleton=False):
        if singleton:
            self.pidfile = self.module / '.google-font-provider.lock/pid'
            self.command = ['sh', str(self.module / 'common/google_font_provider_service.sh')]
        self.pidfile.parent.mkdir(parents=True, exist_ok=True)
        self.pidfile.write_text(text)
        for suffix, value in (('.boot', boot), ('.start', start), ('.task', task)):
            if value is not None:
                Path(str(self.pidfile) + suffix).write_text(value + '\n')

    def snapshot(self):
        return {str(path.relative_to(self.module)): path.read_bytes()
                for path in self.module.rglob('*') if path.is_file()}

    @contextlib.contextmanager
    def mocked_processes(self):
        def read_bytes(path):
            if str(path) == '/proc/4000/cmdline':
                return '\0'.join(self.command).encode() + b'\0'
            return REAL_READ_BYTES(path)

        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(Path, 'iterdir', lambda path: iter([Path('/proc/4000')]) if str(path) == '/proc' else REAL_ITERDIR(path)))
            stack.enter_context(patch.object(Path, 'read_bytes', read_bytes))
            stack.enter_context(patch.object(SCOPE, 'identity', lambda pid: self.record.copy() if self.live else None))
            stack.enter_context(patch.object(SCOPE, 'process_tree', return_value={}))
            stack.enter_context(patch.object(SCOPE, 'signal_record', side_effect=lambda record, number: self.signals.append((record['pid'], number))))
            stack.enter_context(patch.object(SCOPE, 'same_process', return_value=False))
            # Belt-and-braces guards: even an unexpected implementation path
            # cannot deliver an OS signal from this test process.
            stack.enter_context(patch.object(SCOPE.os, 'kill', side_effect=AssertionError('real os.kill forbidden')))
            if hasattr(SCOPE.os, 'pidfd_open'):
                stack.enter_context(patch.object(SCOPE.os, 'pidfd_open', side_effect=AssertionError('real pidfd_open forbidden')))
            if hasattr(signal, 'pidfd_send_signal'):
                stack.enter_context(patch.object(signal, 'pidfd_send_signal', side_effect=AssertionError('real pidfd signal forbidden')))
            yield

    def invoke(self, cancel_all=False):
        with self.mocked_processes(), contextlib.redirect_stdout(io.StringIO()) as output:
            if cancel_all:
                with patch.object(sys, 'argv', ['task_scope.py', 'cancel-all', str(self.module)]):
                    code = SCOPE.main()
            else:
                code = SCOPE.legacy_cancel(self.pidfile, self.module)
        records = [json.loads(line) for line in output.getvalue().splitlines() if line.strip()]
        return code, records

    def assert_refused(self, cancel_all=False):
        before = self.snapshot()
        code, messages = self.invoke(cancel_all=cancel_all)
        self.assertEqual(code, 125)
        self.assertEqual(self.signals, [], 'an unverified identity must not be signaled')
        self.assertEqual(self.snapshot(), before, 'refusal must preserve all evidence byte-for-byte')
        errors = [message for message in messages if message.get('status') == 'error']
        self.assertTrue(errors, 'refusal must explain its reason')
        self.assertTrue(any(isinstance(message.get('data', {}).get('reason'), str)
                            and message['data']['reason']
                            and message['data'].get('pidFile') == str(self.pidfile)
                            for message in errors), messages)

    def test_reused_pid_unrelated_command_is_not_cleaned_or_signaled(self):
        self.register(start='100')
        self.command = ['sleep', '600']
        self.assert_refused()

    def test_standard_start_sidecar_mismatch_is_not_ignored(self):
        self.register(start='100')
        self.assert_refused()

    def test_inline_start_mismatch_is_preserved(self):
        self.register(text=f'4000\nstarttime=100\nboot_id={SCOPE.BOOT}\n', boot=None, task=None, singleton=True)
        self.assert_refused()

    def test_conflicting_inline_and_sidecar_start_is_preserved(self):
        self.register(text=f'4000\nstarttime=200\nboot_id={SCOPE.BOOT}\n', boot=None, start='100', task=None, singleton=True)
        self.assert_refused()

    def test_reverse_inline_and_sidecar_conflict_is_preserved(self):
        self.register(text=f'4000\nstarttime=100\nboot_id={SCOPE.BOOT}\n', boot=None, start='200', task=None, singleton=True)
        self.assert_refused()

    def test_malformed_start_sidecar_is_preserved(self):
        self.register(start='unknown')
        self.assert_refused()

    def test_missing_boot_is_preserved(self):
        self.register(boot=None)
        self.assert_refused()

    def test_empty_boot_is_not_previous_boot(self):
        self.register(boot='')
        self.assert_refused()

    def test_unknown_boot_is_not_previous_boot(self):
        self.register(boot='unknown')
        self.assert_refused()

    def test_firstboot_timestamp_is_not_kernel_boot_id(self):
        self.register(boot='1785281995000')
        self.assert_refused()

    def test_non_uuid_boot_is_not_previous_boot(self):
        self.register(boot='not-a-boot-id')
        self.assert_refused()

    def test_inline_unknown_boot_is_preserved(self):
        self.register(text='4000\nstarttime=200\nboot_id=unknown\n', boot=None, task=None, singleton=True)
        self.assert_refused()

    def test_malformed_pid_has_diagnostic_and_no_side_effects(self):
        self.register(text='pid=4000\n')
        self.assert_refused()

    def test_protected_pid_has_diagnostic_and_no_side_effects(self):
        self.register(text='1\n')
        self.assert_refused()

    def test_matching_command_with_wrong_task_is_not_owned(self):
        self.register(task='different-task')
        self.assert_refused()

    def test_live_exact_legacy_worker_can_be_canceled(self):
        self.register(start='200')
        code, messages = self.invoke()
        self.assertEqual(code, 0)
        self.assertEqual(self.signals, [(4000, signal.SIGTERM)])
        self.assertFalse(self.pidfile.exists())
        self.assertTrue(any(message.get('data', {}).get('cleaned') is True for message in messages))

    def test_live_exact_legacy_provider_inline_format_can_be_canceled(self):
        self.register(text=f'4000\nstarttime=200\nboot_id={SCOPE.BOOT}\ntoken=abc\ncreated=1\n', boot=None, task=None, singleton=True)
        code, messages = self.invoke()
        self.assertEqual(code, 0)
        self.assertEqual(self.signals, [(4000, signal.SIGTERM)])
        self.assertFalse(self.pidfile.exists())
        self.assertTrue(any(message.get('data', {}).get('cleaned') is True for message in messages))

    def test_valid_previous_boot_preserves_existing_retirement_behavior(self):
        self.register(boot=OLD_BOOT)
        code, _ = self.invoke()
        self.assertEqual(code, 0)
        self.assertEqual(self.signals, [])
        self.assertFalse(self.pidfile.exists())

    def test_absent_parent_preserves_existing_retirement_behavior(self):
        self.register()
        self.live = False
        code, _ = self.invoke()
        self.assertEqual(code, 0)
        self.assertEqual(self.signals, [])
        self.assertFalse(self.pidfile.exists())

    def test_zombie_parent_preserves_existing_retirement_behavior(self):
        self.register()
        self.record['state'] = 'Z'
        code, _ = self.invoke()
        self.assertEqual(code, 0)
        self.assertEqual(self.signals, [])
        self.assertFalse(self.pidfile.exists())

    def test_cancel_all_invalid_owner_json_is_preserved_and_explained(self):
        self.register()
        Path(str(self.pidfile) + '.owner.json').write_text('{invalid json\n')
        self.assert_refused(cancel_all=True)


if __name__ == '__main__':
    unittest.main()
