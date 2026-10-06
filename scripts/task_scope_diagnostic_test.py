#!/usr/bin/env python3
"""Read-only cleanup diagnostics and fail-closed mix-start regressions.

Usage: python3 scripts/task_scope_diagnostic_test.py [repository_or_package_root]

Python cases reuse the redirected /proc fixture, which forbids real signals and
process creation. Shell cases run only fixture launchers in a temporary module;
no task worker, Android mount, installed module, or user's font is touched.
"""
import contextlib
import errno
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch


ROOT = (Path(sys.argv.pop(1)).resolve()
        if len(sys.argv) > 1 and not sys.argv[1].startswith('-')
        else Path(__file__).resolve().parents[1])
PROGRAM = ROOT / 'common/task_scope.py'
ROUTER = ROOT / 'common/legacy_v14_4/mix_router.sh'
_fixture_spec = importlib.util.spec_from_file_location(
    'diagnostic_proc_fixture', Path(__file__).with_name('task_scope_namespace_test.py'))
_fixture_module = importlib.util.module_from_spec(_fixture_spec)
with patch.object(sys, 'argv', [sys.argv[0]]):
    _fixture_spec.loader.exec_module(_fixture_module)
_fixture_module.PROGRAM = PROGRAM
ProcFixture = _fixture_module.ProcFixture
BOOT, OLD_BOOT, NS = _fixture_module.BOOT, _fixture_module.OLD_BOOT, _fixture_module.NS
SELF_PID, TARGET_PID = _fixture_module.SELF_PID, _fixture_module.TARGET_PID


def snapshot(root):
    """Compare entries, bytes, modes and mtimes; reads need not preserve atime."""
    result = {}
    for directory, directories, files in os.walk(root, followlinks=False):
        for name in sorted(directories + files):
            path = Path(directory) / name
            info = path.lstat()
            if path.is_symlink():
                content = ('link', os.readlink(path))
            elif path.is_file():
                content = ('file', path.read_bytes())
            else:
                content = ('directory',)
            # Directory timestamps may change while state migration locks are
            # acquired; file data and all entries are still checked exactly.
            result[str(path.relative_to(root))] = (
                info.st_mode, None if path.is_dir() else info.st_mtime_ns, content)
    return result


class SettledDiagnosticTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='luoshu-settled-diagnostics-')
        self.addCleanup(temporary.cleanup)
        self.fixture = ProcFixture(temporary.name)
        self.pidfile = self.fixture.module / 'config/axes_worker.pid'
        self.pidfile.parent.mkdir(parents=True)

    def register(self, pidfile=None, *, pid=TARGET_PID, boot=BOOT, legacy=False):
        pidfile = pidfile or self.pidfile
        pidfile.parent.mkdir(parents=True, exist_ok=True)
        record = dict(procPid=pid, pid=pid, parent=SELF_PID, state='S',
                      start='200', namespace=NS, boot=boot,
                      task='fixture-task', pidfile=str(pidfile))
        for suffix, key in (('', 'pid'), ('.task', 'task'), ('.start', 'start'), ('.boot', 'boot')):
            Path(str(pidfile) + suffix).write_text(str(record[key]) + '\n')
        if not legacy:
            Path(str(pidfile) + '.owner.json').write_text(json.dumps(record))
        return record

    def proof(self, record=None, **changes):
        proof = dict(schema='task-cleanup-v2', task='fixture-task', pid=TARGET_PID,
                     start='200', boot=BOOT, namespace=NS, cleaned=True,
                     leftoverPids=[], cleanupErrors=[], handoffOwners=[], handoffTasks=[])
        if record:
            proof.update({key: record[key] for key in ('task', 'pid', 'start', 'boot', 'namespace')})
        proof.update(changes)
        Path(str(self.pidfile) + '.cleanup.json').write_text(json.dumps(proof))
        return proof

    def invoke(self, scope, diagnostic):
        args = [str(PROGRAM), 'settled', str(self.pidfile)]
        if diagnostic:
            args.append('--diagnostic')
        with patch.object(sys, 'argv', args), \
                contextlib.redirect_stdout(io.StringIO()) as output, \
                contextlib.redirect_stderr(io.StringIO()) as errors:
            result = scope.main()
        self.assertEqual(errors.getvalue(), '')
        return result, output.getvalue()

    def assert_case(self, expected_code, reason=None, *, identity_error=False):
        before = snapshot(self.fixture.module)
        with self.fixture.active():
            scope = self.fixture.load()
            with contextlib.ExitStack() as stack:
                for name in ('atomic', 'cleanup', 'signal_record', 'remove_owner'):
                    if hasattr(scope, name):
                        stack.enter_context(patch.object(
                            scope, name, side_effect=AssertionError('inspection called mutator ' + name)))
                plain_code, plain_text = self.invoke(scope, False)
                diagnostic_code, diagnostic_text = self.invoke(scope, True)
        self.assertEqual(plain_code, expected_code, plain_text)
        self.assertEqual(diagnostic_code, plain_code, diagnostic_text)
        if identity_error:
            plain, diagnostic = json.loads(plain_text), json.loads(diagnostic_text)
            self.assertEqual(plain, diagnostic, 'existing identity error JSON must remain unchanged')
            self.assertEqual(diagnostic['data']['reason'], 'proc-identity-unavailable')
            self.assertIs(diagnostic['data']['cleaned'], False)
        else:
            self.assertEqual(plain_text, '', 'legacy callers must remain silent')
            self.assertEqual(diagnostic_text, '' if reason is None else 'reason=' + reason + '\n')
        self.assertEqual(snapshot(self.fixture.module), before, 'diagnostics must preserve all task evidence')

    def test_missing_registration_is_safe_absence(self):
        self.assert_case(0)

    def test_live_owner_is_reported_without_signaling(self):
        self.register()
        self.fixture.add_process(TARGET_PID)
        self.assert_case(3, 'owner-live')

    def test_previous_boot_registration_is_safe_absence(self):
        self.register(boot=OLD_BOOT)
        self.assert_case(0)

    def test_malformed_owner_is_not_repaired_or_removed(self):
        self.register()
        Path(str(self.pidfile) + '.owner.json').write_text('{ broken record')
        self.assert_case(125, 'owner-record-invalid')

    def test_owner_sidecar_mismatch_is_invalid(self):
        self.register()
        Path(str(self.pidfile) + '.start').write_text('999\n')
        self.assert_case(125, 'owner-record-invalid')

    def test_legacy_current_boot_remains_unconfirmed(self):
        self.register(legacy=True)
        self.assert_case(125, 'legacy-record-unconfirmed')

    def test_legacy_missing_boot_is_unreadable(self):
        self.register(legacy=True)
        Path(str(self.pidfile) + '.boot').unlink()
        self.assert_case(125, 'legacy-boot-unreadable')

    def test_legacy_boot_permission_denied_is_distinct(self):
        self.register(legacy=True)
        self.fixture.open_errors[str(self.pidfile) + '.boot'] = PermissionError(errno.EACCES, 'fixture private path')
        self.assert_case(125, 'permission-denied')

    def test_owner_without_cleanup_proof_is_not_settled(self):
        self.register()
        self.assert_case(125, 'cleanup-proof-missing')

    def test_malformed_cleanup_proof_is_unreadable(self):
        self.register()
        Path(str(self.pidfile) + '.cleanup.json').write_text('{ broken proof')
        self.assert_case(125, 'cleanup-proof-unreadable')

    def test_non_object_cleanup_proof_is_invalid(self):
        self.register()
        Path(str(self.pidfile) + '.cleanup.json').write_text('[]\n')
        self.assert_case(125, 'cleanup-proof-invalid')

    def test_unclean_proof_remains_unconfirmed(self):
        self.proof(self.register(), cleaned=False)
        self.assert_case(125, 'cleanup-proof-unconfirmed')

    def test_cleanup_errors_remain_unconfirmed(self):
        self.proof(self.register(), cleanupErrors=['private /data/path\nnot for the user'])
        self.assert_case(125, 'cleanup-proof-unconfirmed')

    def test_proof_for_another_task_is_unconfirmed(self):
        self.proof(self.register(), task='unrelated-task')
        self.assert_case(125, 'cleanup-proof-unconfirmed')

    def test_cleanup_proof_permission_denied_is_distinct(self):
        self.proof(self.register())
        self.fixture.open_errors[str(self.pidfile) + '.cleanup.json'] = PermissionError(errno.EACCES, 'fixture private path')
        self.assert_case(125, 'permission-denied')

    def test_cleanup_proof_io_error_is_unreadable(self):
        self.proof(self.register())
        self.fixture.open_errors[str(self.pidfile) + '.cleanup.json'] = OSError(errno.EIO, 'fixture private path')
        self.assert_case(125, 'cleanup-proof-unreadable')

    def test_matching_clean_proof_remains_success(self):
        self.proof(self.register())
        self.assert_case(0)

    def test_old_proof_without_owner_is_safe_absence(self):
        self.proof(boot=OLD_BOOT)
        self.assert_case(0)

    def test_live_handoff_reports_live_without_signaling(self):
        record = self.register()
        child = self.register(self.fixture.module / 'config/child.pid', pid=TARGET_PID + 1)
        self.fixture.add_process(TARGET_PID + 1)
        self.proof(record, handoffOwners=[child], handoffTasks=[child['task']])
        self.assert_case(3, 'handoff-live')

    def test_unproved_handoff_remains_unconfirmed(self):
        record = self.register()
        child = self.register(self.fixture.module / 'config/child.pid', pid=TARGET_PID + 1)
        self.proof(record, handoffOwners=[child], handoffTasks=[child['task']])
        self.assert_case(125, 'handoff-unconfirmed')

    def test_proc_permission_error_keeps_existing_rc126_json(self):
        self.register()
        self.fixture.add_process(TARGET_PID)
        self.fixture.open_errors['/proc/%s/stat' % TARGET_PID] = PermissionError(errno.EACCES, 'fixture unreadable process')
        self.assert_case(126, identity_error=True)

    def test_unverified_namespace_keeps_existing_rc126_json(self):
        self.register()
        self.fixture.readlink_errors['/proc/self/ns/pid'] = PermissionError(errno.EACCES, 'fixture namespace denied')
        # A record whose namespace is None exercises the existing unavailable
        # identity path without granting any fallback or signal permission.
        record_path = Path(str(self.pidfile) + '.owner.json')
        record = json.loads(record_path.read_text())
        record['namespace'] = None
        record_path.write_text(json.dumps(record))
        self.assert_case(126, identity_error=True)


STUB_RUNNER = r'''#!/bin/sh
printf '%s|%s|%s\n' "$1" "${2##*/}" "${3:-}" >> "$DIAGNOSTIC_CALLS"
case "$1" in
    settled)
        case "${2##*/}" in
            "$DIAGNOSTIC_SLOT")
                printf '%s' "$DIAGNOSTIC_STDOUT"
                printf '%s' "$DIAGNOSTIC_STDERR" >&2
                exit "$DIAGNOSTIC_RC" ;;
        esac
        [ "${2##*/}" != "${DIAGNOSTIC_LIVE_SLOT:-}" ] || {
            printf 'reason=owner-live\n'
            exit 3
        }
        exit 0 ;;
    cleaned) [ "${2##*/}" = "${DIAGNOSTIC_CLEAN_SLOT:-}" ]; exit $? ;;
    *) printf 'unexpected mutation: %s\n' "$1" >&2; exit 98 ;;
esac
'''


class MixRouterDiagnosticTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='luoshu-mix-diagnostics-')
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.module = self.directory / 'module'
        common = self.module / 'common'
        common.mkdir(parents=True)
        (self.module / 'module.prop').write_text('id=LuoShu\n')
        for name in ('task_scope.sh', 'task_scope.py', 'background_task.sh',
                     'runtime_paths.sh', 'runtime_paths_lock.py',
                     'font_next_transaction.sh', 'font_switch_lock.sh'):
            (common / name).symlink_to(ROOT / 'common' / name)
        self.calls = self.directory / 'calls.log'
        self.runner = self.directory / 'fixture-runner.sh'
        self.runner.write_text(STUB_RUNNER)
        self.env = {name: value for name, value in os.environ.items()
                    if not name.startswith('LUOSHU_') and name not in ('MODDIR', 'MODULE_DIR', 'PYTHONHOME', 'PYTHONPATH')}
        self.env.update(MODDIR=str(self.module),
                        LUOSHU_TASK_SCOPE_RUNNER=str(self.runner),
                        LUOSHU_RUNTIME_PATHS_PYTHON=sys.executable,
                        LUOSHU_TASK_SCOPE_PYTHON=sys.executable,
                        DIAGNOSTIC_CALLS=str(self.calls),
                        DIAGNOSTIC_SLOT='axes_worker.pid', DIAGNOSTIC_RC='125',
                        DIAGNOSTIC_STDOUT='reason=cleanup-proof-missing\n', DIAGNOSTIC_STDERR='')
        initialized = subprocess.run(
            ['sh', '-c', '. "$MODDIR/common/runtime_paths.sh"; luoshu_runtime_paths_init "$MODDIR"'],
            env=self.env, capture_output=True, text=True, timeout=5)
        self.assertEqual(initialized.returncode, 0, initialized.stdout + initialized.stderr)
        self.conf = self.module / 'config/axes_task.conf'
        self.configure()
        for relative in ('.luoshu-payload', '.luoshu-payload-next', '.luoshu-state/tmp/mix-stage'):
            target = self.module / relative
            (target / 'fonts').mkdir(parents=True)
            (target / 'fonts/preserved.ttf').write_bytes(b'\x00fixture old font\xff')
            (target / 'generation.conf').write_text('task=old-generation\n')
        for name in ('font-payload-next.conf', 'mix-stage-next.conf', 'active_font.conf'):
            (self.module / 'config' / name).write_text('preserved=' + name + '\n')
        for slot in ('axes_worker.pid', 'auto_multiweight_worker.pid', 'mix_worker.pid',
                     'mix-monitor-private-child-token-123.pid'):
            (self.module / '.luoshu-state/tasks' / (slot + '.owner.json')).write_text(
                '{\"private\":\"preserved ownership evidence\"}\n')
        definitions, marker, _ = ROUTER.read_text().partition('\n_cmd=')
        self.assertTrue(marker, 'router command-dispatch boundary must be found')
        self.probe = self.directory / 'scope-probe.sh'
        self.probe.write_text(definitions + '\nmix_scope_state_fast "$DIAGNOSTIC_CONF" "${1:-}"\nexit $?\n')
        self.env['DIAGNOSTIC_CONF'] = str(self.conf)

    def configure(self, state='idle', **values):
        config = dict(task='fixture-controller', childTask='private-child-token-123',
                      state=state, started=str(int(time.time())), message='original task message')
        config.update(values)
        self.conf.write_text(''.join(str(key) + '=' + str(value) + '\n' for key, value in config.items()))

    def run_probe(self, diagnostic=True):
        arguments = ['sh', str(self.probe)] + (['diagnostic'] if diagnostic else [])
        return subprocess.run(arguments, env=self.env, capture_output=True, text=True, timeout=8)

    def preserved(self):
        roots = ('.luoshu-payload', '.luoshu-payload-next', '.luoshu-state/tmp/mix-stage',
                 '.luoshu-state/config', '.luoshu-state/tasks', '.luoshu-state/backup')
        return {root: snapshot(self.module / root) for root in roots}

    def assert_safe(self, text):
        self.assertLessEqual(len(text.encode('utf-8')), 2048, 'diagnostic output must stay bounded')
        for private in ('PRIVATE_STDERR', 'PRIVATE_STDOUT', 'private-child-token-123',
                        '/private/device/path', str(self.directory)):
            self.assertNotIn(private, text)
        self.assertNotIn('\r', text)
        self.assertNotIn('\x1b', text)
        self.assertLessEqual(len(text.splitlines()), 4)

    def assert_refused(self, label='axes_worker', rc=125, prefix=None, reconciles=False):
        before = self.preserved()
        result = subprocess.run(['sh', str(ROUTER), 'start', 'new-cjk', 'new-latin', 'new-digit'],
                                env=self.env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(result.stderr, '')
        self.assertEqual(len(result.stdout.splitlines()), 1, 'one complete JSON response is required')
        response = json.loads(result.stdout)
        self.assertEqual(response['status'], 'error')
        self.assertIn(label + ': rc=' + str(rc), response['message'])
        if prefix:
            self.assertIn(prefix, response['message'])
        self.assert_safe(response['message'])
        after = self.preserved()
        if reconciles:
            # Existing reconciliation may update only the public task card.
            # Every payload, owner record and other config must remain intact.
            before['.luoshu-state/config'].pop('axes_task.conf', None)
            after['.luoshu-state/config'].pop('axes_task.conf', None)
        self.assertEqual(after, before, 'start refusal must leave old payloads and records untouched')
        return response

    def test_optional_probe_diagnostic_keeps_exit_code_and_silent_default(self):
        before = self.preserved()
        plain = self.run_probe(False)
        diagnostic = self.run_probe(True)
        self.assertEqual(plain.returncode, 125, plain.stderr)
        self.assertEqual(plain.stdout, '')
        self.assertEqual(plain.stderr, '')
        self.assertEqual(diagnostic.returncode, plain.returncode)
        self.assertEqual(diagnostic.stderr, '')
        self.assertIn('axes_worker: rc=125', diagnostic.stdout)
        self.assertIn('清理证明缺失', diagnostic.stdout)
        self.assert_safe(diagnostic.stdout)
        calls = self.calls.read_text().splitlines()
        settled = [line for line in calls if line.startswith('settled|')]
        self.assertEqual(len(settled), 8)
        self.assertTrue(all('--diagnostic' not in line for line in settled[:4]))
        self.assertTrue(all('--diagnostic' in line for line in settled[4:]))
        self.assertEqual(self.preserved(), before)

    def test_safe_absence_still_returns_one_without_error_text(self):
        self.env['DIAGNOSTIC_SLOT'] = 'not-an-inspected-slot'
        for diagnostic in (False, True):
            with self.subTest(diagnostic=diagnostic):
                result = self.run_probe(diagnostic)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, '')
                self.assertEqual(result.stderr, '')

    def test_exact_cleanup_still_returns_zero_without_error_text(self):
        self.env.update(DIAGNOSTIC_SLOT='not-an-inspected-slot', DIAGNOSTIC_CLEAN_SLOT='mix_worker.pid')
        for diagnostic in (False, True):
            with self.subTest(diagnostic=diagnostic):
                result = self.run_probe(diagnostic)
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stdout, '')
                self.assertEqual(result.stderr, '')

    def test_live_slot_still_takes_precedence_over_unknown(self):
        self.env['DIAGNOSTIC_LIVE_SLOT'] = 'mix_worker.pid'
        plain, diagnostic = self.run_probe(False), self.run_probe(True)
        self.assertEqual(plain.returncode, 3)
        self.assertEqual(diagnostic.returncode, 3)
        self.assertIn('axes_worker: rc=125', diagnostic.stdout)
        self.assertIn('mix_worker: rc=3', diagnostic.stdout)
        self.assert_safe(diagnostic.stdout)

    def test_each_slot_is_identified_without_dynamic_monitor_task(self):
        for slot, label in (('axes_worker.pid', 'axes_worker'),
                            ('auto_multiweight_worker.pid', 'auto_multiweight_worker'),
                            ('mix_worker.pid', 'mix_worker'),
                            ('mix-monitor-private-child-token-123.pid', 'mix-monitor')):
            with self.subTest(slot=slot):
                self.env['DIAGNOSTIC_SLOT'] = slot
                self.assert_refused(label=label,
                                    prefix='上一字体组合任务清理尚未确认')

    def test_queued_start_refusal_includes_diagnostic_and_preserves_stage(self):
        self.configure(state='queued')
        self.assert_refused(prefix='已有字体组合任务正在运行或等待清理')

    def test_running_start_refusal_includes_diagnostic_and_preserves_stage(self):
        self.configure(state='running')
        self.assert_refused(prefix='已有字体组合任务正在运行或等待清理')

    def test_cleanup_pending_start_refusal_preserves_all_payloads(self):
        self.configure(state='cleanup-pending')
        self.assert_refused(prefix='已有字体组合任务正在运行或等待清理', reconciles=True)
        self.assertIn('state=cleanup-pending\n', self.conf.read_text())
        self.assertIn('cleanupConfirmed=false\n', self.conf.read_text())

    def test_no_task_config_still_identifies_the_blocking_slot(self):
        self.conf.unlink()
        self.assert_refused(prefix='上一字体组合任务清理尚未确认')
        self.assertFalse(self.conf.exists())

    def test_empty_task_config_still_identifies_the_blocking_slot(self):
        self.conf.write_text('')
        self.assert_refused(prefix='上一字体组合任务清理尚未确认')
        self.assertEqual(self.conf.read_text(), '')

    def test_each_fixed_reason_has_safe_human_readable_translation(self):
        for token, expected in (
                ('owner-live', '旧任务仍在运行'),
                ('handoff-live', '移交的子任务仍在运行'),
                ('owner-record-invalid', '任务身份记录不完整、不匹配或不可读'),
                ('legacy-record-unconfirmed', '旧任务记录尚未确认退出'),
                ('legacy-boot-unreadable', '旧任务启动标记缺失或不可读'),
                ('cleanup-proof-missing', '任务清理证明缺失'),
                ('cleanup-proof-invalid', '任务清理证明格式无效'),
                ('cleanup-proof-unconfirmed', '任务清理证明不匹配或未完成'),
                ('handoff-unconfirmed', '移交子任务的清理未确认'),
                ('cleanup-proof-unreadable', '任务清理证明不可读或损坏'),
                ('permission-denied', '权限不足，无法读取任务证据')):
            with self.subTest(token=token):
                rc = 3 if token.endswith('-live') else 125
                self.env.update(DIAGNOSTIC_RC=str(rc), DIAGNOSTIC_STDOUT='reason=' + token + '\n')
                response = self.assert_refused(rc=rc)
                self.assertIn(expected, response['message'])

    def test_multiline_hostile_stderr_is_never_echoed(self):
        self.env['DIAGNOSTIC_STDERR'] = ('PRIVATE_STDERR /private/device/path "quoted"\n\r\x1b[31m' * 500)
        response = self.assert_refused()
        self.assertIn('清理证明缺失', response['message'])

    def test_unknown_hostile_stdout_uses_only_safe_fallback(self):
        self.env['DIAGNOSTIC_STDOUT'] = ('reason=PRIVATE_STDOUT /private/device/path\n"quote"\r\x1b[31m' * 500)
        self.assert_refused()

    def test_real_scope_launcher_rc126_is_retained_in_refusal(self):
        self.env.pop('LUOSHU_TASK_SCOPE_RUNNER')
        self.env['LUOSHU_TASK_SCOPE_PYTHON'] = str(self.directory / 'missing-launcher')
        response = self.assert_refused(rc=126)
        for label in ('axes_worker', 'auto_multiweight_worker', 'mix_worker', 'mix-monitor'):
            self.assertEqual(response['message'].count(label + ': rc=126'), 1)

    def test_real_scope_launcher_rc127_is_retained_without_stderr(self):
        launcher = self.directory / 'unavailable-interpreter'
        launcher.write_text('#!/bin/sh\nprintf \'PRIVATE_STDERR /private/device/path\\n\' >&2\nexit 127\n')
        launcher.chmod(0o700)
        self.env.pop('LUOSHU_TASK_SCOPE_RUNNER')
        self.env['LUOSHU_TASK_SCOPE_PYTHON'] = str(launcher)
        self.assert_refused(rc=127)

    def test_proc_identity_json_is_translated_without_exposing_private_detail(self):
        self.env.update(DIAGNOSTIC_RC='126', DIAGNOSTIC_STDOUT=json.dumps({
            'status': 'error', 'data': {'cleaned': False, 'reason': 'proc-identity-unavailable'},
            'message': 'PRIVATE_STDOUT /private/device/path\n' + 'x' * 10000}))
        self.assert_refused(rc=126)


if __name__ == '__main__':
    unittest.main()
