#!/usr/bin/env python3
"""Real mksh/dash task-slot parsing and supervisor safety regressions.

Usage: python3 scripts/task_scope_mksh_test.py [repository_or_package_root]
Set LUOSHU_TEST_MKSH to an explicit mksh binary, or install mksh in CI.

Every module and payload is a temporary fixture. Checks use the real supervisor;
only cancellation-routing tests replace cancel with a non-signaling recorder.
Live inspection uses a bounded child created and cleaned up by this test only.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = (Path(sys.argv.pop(1)).resolve()
        if len(sys.argv) > 1 and not sys.argv[1].startswith('-')
        else Path(__file__).resolve().parents[1])
ROUTER = ROOT / 'common/legacy_v14_4/mix_router.sh'
MKSH = os.environ.get('LUOSHU_TEST_MKSH') or shutil.which('mksh')
DASH = shutil.which('dash')
if not MKSH or not Path(MKSH).is_file() or not os.access(MKSH, os.X_OK):
    raise SystemExit('mksh is required: install the official package in CI or set LUOSHU_TEST_MKSH to its executable')
if not DASH:
    raise SystemExit('dash is required for the POSIX-shell parity checks')
SHELLS = (('mksh', str(Path(MKSH).resolve())), ('dash', str(Path(DASH).resolve())))
BOOT = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
OLD_BOOT = '00000000-0000-4000-8000-000000000001'
if OLD_BOOT == BOOT:
    OLD_BOOT = '00000000-0000-4000-8000-000000000002'
NS = os.readlink('/proc/self/ns/pid')
FROZEN_MANIFEST = Path(__file__).with_name('stable111_frozen_runtime.json')
FROZEN = json.loads(FROZEN_MANIFEST.read_text())['sha256']


def frozen_hashes():
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in FROZEN}


def snapshot(root):
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
            result[str(path.relative_to(root))] = (
                info.st_mode, None if path.is_dir() else info.st_mtime_ns, content)
    return result


# Transparent observation of real supervisor calls. Cancel is replaced only
# when a routing test explicitly requests it, and always fails closed there.
TRACK_RUNNER = r'''#!/bin/sh
printf '%s\t%s\t%s\n' "$1" "$2" "${3:-}" >> "$LUOSHU_TEST_CALLS"
if [ "${LUOSHU_TEST_RECORD_CANCEL:-}" = 1 ] && [ "$1" = cancel ]; then
    printf '{"status":"error","data":{"cleaned":false},"message":"fixture cancel recorder"}\n'
    exit 125
fi
exec sh "$MODDIR/common/task_scope.sh" "$@"
'''


class ShellParsingTests(unittest.TestCase):
    def test_real_mksh_binary_is_required(self):
        result = subprocess.run([MKSH, '-c', 'printf "%s\\n" "$KSH_VERSION"'],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('MIRBSD KSH', result.stdout, 'the regression must run actual mksh')

    def test_unescaped_pipe_reproduces_mksh_failure(self):
        expression = 'slot=$1; printf "%s\\n%s\\n" "${slot%%|*}" "${slot#*|}"'
        pair = 'mix_worker.pid|child-task'
        for name, shell in SHELLS:
            with self.subTest(shell=name):
                result = subprocess.run([shell, '-c', expression, 'fixture', pair],
                                        capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr)
                expected = ['', pair] if name == 'mksh' else ['mix_worker.pid', 'child-task']
                self.assertEqual(result.stdout.splitlines(), expected)

    def test_escaped_pipe_has_mksh_dash_parity(self):
        expression = r'slot=$1; printf "%s\n%s\n" "${slot%%\|*}" "${slot#*\|}"'
        for basename, task in (('axes_worker.pid', 'controller.12'),
                               ('auto_multiweight_worker.pid', 'controller.12'),
                               ('mix_worker.pid', 'child-task'),
                               ('mix-monitor-child-task.pid', 'child-task.monitor'),
                               ('mix-monitor-.pid', '.monitor'),
                               ('axes_worker.pid', '')):
            for name, shell in SHELLS:
                with self.subTest(shell=name, slot=basename, task=task):
                    result = subprocess.run([shell, '-c', expression, 'fixture', basename + '|' + task],
                                            capture_output=True, text=True, timeout=5)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout.splitlines(), [basename, task])


class RealSupervisorShellTests(unittest.TestCase):
    def setUp(self):
        self.frozen_before = frozen_hashes()
        temporary = tempfile.TemporaryDirectory(prefix='luoshu-mksh-scope-')
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.module = self.directory / 'module'
        common = self.module / 'common'
        common.mkdir(parents=True)
        (self.module / 'module.prop').write_text('id=LuoShu\n')
        for name in ('task_scope.sh', 'task_scope.py', 'background_task.sh', 'runtime_paths.sh',
                     'runtime_paths_lock.py', 'font_next_transaction.sh', 'font_switch_lock.sh'):
            (common / name).symlink_to(ROOT / 'common' / name)
        self.bin = self.directory / 'bin'
        self.bin.mkdir()
        self.calls = self.directory / 'supervisor-calls.tsv'
        self.runner = self.directory / 'tracking-runner.sh'
        self.runner.write_text(TRACK_RUNNER)
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith('LUOSHU_') and key not in ('MODDIR', 'MODULE_DIR', 'PYTHONHOME', 'PYTHONPATH')}
        self.env.update(MODDIR=str(self.module), LUOSHU_TASK_SCOPE_PYTHON=sys.executable,
                        LUOSHU_RUNTIME_PATHS_PYTHON=sys.executable,
                        LUOSHU_TASK_SCOPE_RUNNER=str(self.runner), LUOSHU_TEST_CALLS=str(self.calls))
        self.original_path = self.env.get('PATH', os.defpath)
        self.select_shell(SHELLS[0][1])
        initialized = subprocess.run([self.shell, '-c',
                                     '. "$MODDIR/common/runtime_paths.sh"; luoshu_runtime_paths_init "$MODDIR"'],
                                    env=self.env, capture_output=True, text=True, timeout=10)
        self.assertEqual(initialized.returncode, 0, initialized.stdout + initialized.stderr)
        self.tasks = self.module / '.luoshu-state/tasks'
        self.conf = self.module / 'config/axes_task.conf'
        self.configure()
        for relative in ('.luoshu-payload', '.luoshu-payload-next', '.luoshu-state/tmp/mix-stage'):
            target = self.module / relative
            (target / 'fonts').mkdir(parents=True)
            (target / 'fonts/preserved.ttf').write_bytes(b'\x00existing fixture font\xff')
            (target / '.generation.conf').write_text('task=existing-generation\n')
        for name in ('font-payload-next.conf', 'mix-stage-next.conf', 'active_font.conf'):
            (self.module / 'config' / name).write_text('preserved=' + name + '\n')
        definitions, marker, _ = ROUTER.read_text().partition('\n_cmd=')
        self.assertTrue(marker, 'router function-definition boundary must be found')
        self.probe = self.directory / 'scope-probe.sh'
        self.probe.write_text(definitions + '\nmix_scope_state_fast "$LUOSHU_TEST_CONF" "${1:-}"\nexit $?\n')
        self.env['LUOSHU_TEST_CONF'] = str(self.conf)
        self.addCleanup(self.assert_frozen_unchanged)

    def assert_frozen_unchanged(self):
        self.assertEqual(frozen_hashes(), self.frozen_before, 'tests must not alter any frozen runtime source')

    def select_shell(self, shell):
        self.shell = shell
        link = self.bin / 'sh'
        link.unlink(missing_ok=True)
        link.symlink_to(shell)
        self.env['PATH'] = str(self.bin) + os.pathsep + self.original_path

    def configure(self, *, child='fixture-child'):
        self.task = 'fixture-controller'
        self.child = child or self.task
        values = [('task', self.task), ('state', 'idle'), ('started', '1')]
        if child is not None:
            values.append(('childTask', child))
        self.conf.write_text(''.join(key + '=' + value + '\n' for key, value in values))

    def slots(self):
        return [('axes_worker.pid', self.task), ('auto_multiweight_worker.pid', self.task),
                ('mix_worker.pid', self.child), ('mix-monitor-' + self.child + '.pid', self.child + '.monitor')]

    def register(self, slot, task, *, boot=BOOT, record=True, process=None):
        pidfile = self.tasks / slot
        pid = process.pid if process else 2147483647
        start = Path('/proc/%s/stat' % pid).read_text().rsplit(') ', 1)[1].split()[19] if process else '200'
        owner = dict(procPid=pid, pid=pid, parent=os.getpid(), start=start, state='S',
                     boot=boot, namespace=NS, task=task, pidfile=str(pidfile))
        for suffix, key in (('', 'pid'), ('.task', 'task'), ('.start', 'start'), ('.boot', 'boot')):
            Path(str(pidfile) + suffix).write_text(str(owner[key]) + '\n')
        if record:
            Path(str(pidfile) + '.owner.json').write_text(json.dumps(owner))
        return pidfile

    def clear_registrations(self):
        for path in self.tasks.iterdir():
            self.assertTrue(path.is_file(), 'only test-owned registration files may be reset')
            path.unlink()

    def invoke(self, *arguments, probe=False):
        self.calls.write_text('')
        before = snapshot(self.module)
        command = [self.shell, str(self.probe if probe else ROUTER), *arguments]
        result = subprocess.run(command, env=self.env, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.stderr, '', result.stderr)
        self.assertEqual(snapshot(self.module), before,
                         'inspection or failed cancellation changed registrations, config, or payloads')
        self.assert_frozen_unchanged()
        calls = [line.split('\t') for line in self.calls.read_text().splitlines()]
        for action, path, token in calls:
            self.assertEqual(Path(path).parent, self.tasks, 'a supervisor call must stay in the task directory')
            self.assertNotEqual(Path(path), self.tasks, 'never inspect or cancel the parent tasks directory')
            self.assertTrue(Path(path).name.endswith('.pid'), (action, path, token))
        return result, calls

    def assert_probe(self, code, label=None, reason=None, *, diagnostic=True):
        result, calls = self.invoke(*(['diagnostic'] if diagnostic else []), probe=True)
        self.assertEqual(result.returncode, code, result.stdout)
        inspected = [Path(path).name for action, path, _ in calls if action == 'settled']
        self.assertEqual(inspected, [slot for slot, _ in self.slots()])
        if label:
            self.assertIn(label + ': rc=' + str(code), result.stdout)
            self.assertNotIn('supervisor:', result.stdout)
            if reason:
                self.assertIn(reason, result.stdout)
        else:
            self.assertEqual(result.stdout, '')
        return result, calls

    def test_frozen_runtime_matches_approved_baseline(self):
        self.assertEqual(self.frozen_before, FROZEN)

    def test_no_task_record_has_safe_absence_in_both_shells(self):
        self.conf.unlink()
        self.task = self.child = ''
        for name, shell in SHELLS:
            for diagnostic in (False, True):
                with self.subTest(shell=name, diagnostic=diagnostic):
                    self.select_shell(shell)
                    self.assert_probe(1, diagnostic=diagnostic)

    def test_fresh_task_config_has_no_false_cleanup_failure(self):
        for name, shell in SHELLS:
            with self.subTest(shell=name):
                self.select_shell(shell)
                self.assert_probe(1)

    def test_confirmed_safe_absence_remains_zero(self):
        with self.conf.open('a') as output:
            output.write('cleanupConfirmed=true\n')
        for name, shell in SHELLS:
            with self.subTest(shell=name):
                self.select_shell(shell)
                self.assert_probe(0)

    def test_malformed_owner_reports_each_actual_slot(self):
        for slot, task in self.slots():
            self.clear_registrations()
            pidfile = self.register(slot, task)
            Path(str(pidfile) + '.owner.json').write_text('{broken owner')
            label = 'mix-monitor' if slot.startswith('mix-monitor-') else slot.removesuffix('.pid')
            for name, shell in SHELLS:
                with self.subTest(shell=name, slot=slot):
                    self.select_shell(shell)
                    self.assert_probe(125, label, '任务身份记录')
                    result, _ = self.invoke('start', 'new-cjk', 'new-latin', 'new-digit')
                    self.assertEqual(result.returncode, 1)
                    response = json.loads(result.stdout)
                    self.assertEqual(response['status'], 'error')
                    self.assertIn(label + ': rc=125', response['message'])
                    self.assertNotIn('supervisor:', response['message'])

    def test_current_boot_owner_without_proof_remains_unconfirmed(self):
        self.register('mix_worker.pid', self.child)
        for name, shell in SHELLS:
            with self.subTest(shell=name):
                self.select_shell(shell)
                self.assert_probe(125, 'mix_worker', '任务清理证明缺失')

    def test_current_legacy_registration_remains_unconfirmed(self):
        self.register('mix-monitor-' + self.child + '.pid', self.child + '.monitor', record=False)
        for name, shell in SHELLS:
            with self.subTest(shell=name):
                self.select_shell(shell)
                self.assert_probe(125, 'mix-monitor', '旧任务记录尚未确认退出')

    def test_missing_legacy_boot_stays_fail_closed_with_real_slot(self):
        pidfile = self.register('mix_worker.pid', self.child, record=False)
        Path(str(pidfile) + '.boot').unlink()
        for name, shell in SHELLS:
            with self.subTest(shell=name):
                self.select_shell(shell)
                self.assert_probe(125, 'mix_worker', '旧任务启动标记缺失或不可读')

    def test_previous_boot_registration_is_safe_in_each_shell(self):
        for legacy in (False, True):
            self.clear_registrations()
            self.register('mix_worker.pid', self.child, boot=OLD_BOOT, record=not legacy)
            for name, shell in SHELLS:
                with self.subTest(shell=name, legacy=legacy):
                    self.select_shell(shell)
                    self.assert_probe(0)

    def test_live_test_owned_process_is_three_without_signaling(self):
        process = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            pidfile = self.register('mix_worker.pid', self.child, process=process)
            for name, shell in SHELLS:
                with self.subTest(shell=name):
                    self.select_shell(shell)
                    self.assert_probe(3, 'mix_worker', '旧任务仍在运行')
                    self.assertIsNone(process.poll(), 'read-only scope checks must not signal the fixture child')
                    self.assertTrue(Path(str(pidfile) + '.owner.json').exists())
        finally:
            # Only this explicitly created child is terminated; no task cancel
            # command or process-name/group matching is used for teardown.
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)

    def test_cancel_routes_exact_engine_monitor_and_task_tokens(self):
        self.env['LUOSHU_TEST_RECORD_CANCEL'] = '1'
        for child in ('fixture-child', None):
            self.configure(child=child)
            self.clear_registrations()
            for slot, task in self.slots():
                self.register(slot, task)
            expected = [('cancel', str(self.tasks / slot), task) for slot, task in self.slots()]
            for name, shell in SHELLS:
                with self.subTest(shell=name, child=child):
                    self.select_shell(shell)
                    result, calls = self.invoke('cancel', self.task)
                    self.assertEqual(result.returncode, 125, result.stdout)
                    self.assertEqual([tuple(call) for call in calls if call[0] == 'cancel'], expected)
                    self.assertIs(json.loads(result.stdout)['data']['cleaned'], False)

    def test_cancel_never_adopts_another_engine_task(self):
        self.env['LUOSHU_TEST_RECORD_CANCEL'] = '1'
        for slot, task in self.slots():
            self.register(slot, 'unrelated-engine-task' if slot == 'mix_worker.pid' else task)
        for name, shell in SHELLS:
            with self.subTest(shell=name):
                self.select_shell(shell)
                result, calls = self.invoke('cancel', self.task)
                self.assertEqual(result.returncode, 125)
                cancelled = [call for call in calls if call[0] == 'cancel']
                self.assertFalse(any(Path(call[1]).name == 'mix_worker.pid' for call in cancelled))
                self.assertTrue(any(action == 'settled' and Path(path).name == 'mix_worker.pid'
                                    for action, path, _ in calls))
                self.assertIn(['cancel', str(self.tasks / ('mix-monitor-' + self.child + '.pid')),
                               self.child + '.monitor'], cancelled)

    def test_real_supervisor_cancel_refusal_preserves_invalid_evidence(self):
        # The real supervisor sees malformed ownership plus matching task
        # sidecars. Its fail-closed refusal cannot identify or signal a process.
        for slot, task in self.slots():
            pidfile = self.register(slot, task)
            Path(str(pidfile) + '.owner.json').write_text('{broken owner')
        expected = [('cancel', str(self.tasks / slot), task) for slot, task in self.slots()]
        for name, shell in SHELLS:
            with self.subTest(shell=name):
                self.select_shell(shell)
                result, calls = self.invoke('cancel', self.task)
                self.assertEqual(result.returncode, 125, result.stdout)
                self.assertEqual([tuple(call) for call in calls if call[0] == 'cancel'], expected)
                response = json.loads(result.stdout)
                self.assertEqual(response['status'], 'error')
                self.assertIs(response['data']['cleaned'], False)


if __name__ == '__main__':
    unittest.main()
