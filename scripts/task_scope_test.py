#!/usr/bin/env python3
"""Real Linux subreaper integration plus deterministic process-identity tests."""
import importlib.util
import errno
import types
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'common/task_scope.py'
spec = importlib.util.spec_from_file_location('task_scope', HELPER)
scope = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scope)


def wait_for(check, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(0.025)
    raise AssertionError('bounded condition did not converge')


def alive(pid):
    info = scope.proc_info(pid)
    return bool(info and info['state'] not in ('Z', 'X'))


class TaskScopeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.module = self.root / 'module'
        self.config = self.module / 'config'
        self.config.mkdir(parents=True)
        self.pidfile = self.config / 'switch_task_worker.pid'
        self.log = self.root / 'task.log'
        self.helper = HELPER
        self.env = dict(os.environ, MODDIR=str(self.module),
                        LUOSHU_TASK_HELPER=str(HELPER), LUOSHU_TASK_TIMEOUT_SECONDS='10')
        self.extra_pids = []
        self.addCleanup(self.cleanup)

    def cleanup(self):
        for file in self.config.glob('*.pid.identity'):
            subprocess.run([sys.executable, str(HELPER), 'stop', str(file)[:-9]],
                           env=self.env, timeout=12, check=False)
        for pid in self.extra_pids:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        self.temp.cleanup()

    def launch(self, code, task='scope-test', pidfile=None, timeout=None):
        env = self.env.copy()
        if timeout is not None:
            env['LUOSHU_TASK_TIMEOUT_SECONDS'] = str(timeout)
        result = subprocess.run([sys.executable, str(self.helper), 'launch',
                                 str(pidfile or self.pidfile), task, str(self.log), '--',
                                 sys.executable, '-c', code], env=env, capture_output=True, timeout=12)
        self.assertEqual(result.returncode, 0, result.stderr.decode() + scope.read(self.log))

    def identity(self, pidfile=None):
        return json.loads(Path(str(pidfile or self.pidfile) + '.identity').read_text())

    def orphan_code(self, mode='success', exitcode=0):
        leaf = str(self.root / ('leaf-' + mode))
        worker = str(self.root / ('worker-' + mode))
        # Double-fork + a new session escapes both PPID snapshots and killpg.
        # The finite subreaper must adopt it, then reap the zombie after KILL.
        return f'''
import os, signal, time
from pathlib import Path
Path({worker!r}).write_text(str(os.getpid()))
if os.fork() == 0:
    os.setsid()
    if os.fork() != 0: os._exit(0)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    Path({leaf!r}).write_text(str(os.getpid()))
    while True: time.sleep(.05)
while not Path({leaf!r}).exists(): time.sleep(.01)
Path(os.environ['LUOSHU_TASK_WORK_DIR'], 'scratch.bin').write_bytes(b'scratch')
{'time.sleep(60)' if mode in ('cancel', 'timeout', 'kill-worker', 'kill-reaper') else 'time.sleep(.1)'}
os._exit({exitcode})
'''

    def assert_clean(self, mode, pidfile=None):
        leaf = int(wait_for(lambda: scope.read(self.root / ('leaf-' + mode))))
        wait_for(lambda: not Path(str(pidfile or self.pidfile) + '.identity').exists())
        self.assertFalse(alive(leaf), f'orphan {leaf} survived task completion')
        self.assertFalse((scope.PROC / str(leaf)).exists(), 'supervisor failed to reap orphan zombie')
        self.assertFalse(list((self.module / 'cache/tasks').glob('*/.luoshu-task-owner')))

    def test_success_reaps_double_forked_setsid_term_ignoring_orphan(self):
        self.launch(self.orphan_code())
        self.assert_clean('success')

    def test_failure_reaps_orphan_and_task_workspace(self):
        self.launch(self.orphan_code('failure', 7))
        self.assert_clean('failure')

    def test_timeout_reaps_orphan_and_publishes_failure(self):
        (self.config / 'switch_task.conf').write_text('task=scope-test\nstate=running\n')
        self.launch(self.orphan_code('timeout'), timeout=.5)
        self.assert_clean('timeout')
        self.assertIn('执行超时', scope.read(self.config / 'switch_task.conf'))

    def test_cancel_does_not_touch_another_concurrent_scope(self):
        other = self.config / 'other.pid'
        self.launch('import time; time.sleep(30)', task='unrelated-task', pidfile=other)
        other_id = self.identity(other)
        self.launch(self.orphan_code('cancel'))
        wait_for(lambda: scope.read(self.root / 'leaf-cancel'))
        subprocess.run([sys.executable, str(HELPER), 'stop', str(self.pidfile)],
                       check=True, timeout=12, env=self.env)
        leaf = int(scope.read(self.root / 'leaf-cancel'))
        self.assertFalse(alive(leaf))
        self.assertTrue(scope.same_process(other_id['owner']))
        subprocess.run([sys.executable, str(HELPER), 'stop', str(other)],
                       check=True, timeout=12, env=self.env)

    def test_sigkill_worker_is_reaped_with_its_orphan(self):
        self.launch(self.orphan_code('kill-worker'))
        worker = int(wait_for(lambda: scope.read(self.root / 'worker-kill-worker')))
        wait_for(lambda: scope.read(self.root / 'leaf-kill-worker'))
        os.kill(worker, signal.SIGKILL)
        self.assert_clean('kill-worker')

    def test_dead_supervisor_can_recover_token_orphan_without_killing_sentinel(self):
        self.launch(self.orphan_code('kill-reaper'))
        leaf = int(wait_for(lambda: scope.read(self.root / 'leaf-kill-reaper')))
        self.extra_pids.append(leaf)
        worker = int(scope.read(self.root / 'worker-kill-reaper'))
        self.extra_pids.append(worker)
        identity = self.identity()
        sentinel = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
        self.addCleanup(lambda: (sentinel.kill() if sentinel.poll() is None else None, sentinel.wait()))
        os.kill(identity['owner']['pid'], signal.SIGKILL)
        wait_for(lambda: not scope.identity_alive(identity))
        # SIGKILL cannot run a trap. Recovery is explicit, never a hidden daemon.
        subprocess.run([sys.executable, str(HELPER), 'stop', str(self.pidfile)],
                       check=True, timeout=12, env=self.env)
        self.assertFalse(alive(leaf))
        self.assertFalse(alive(worker))
        self.assertIsNone(sentinel.poll())
        self.assertFalse(Path(str(self.pidfile) + '.identity').exists())

    def test_same_pidfile_concurrent_launches_have_one_owner(self):
        command = [sys.executable, str(HELPER), 'launch', str(self.pidfile), 'same-task',
                   str(self.log), '--', sys.executable, '-c', 'import time; time.sleep(30)']
        a = subprocess.Popen(command, env=self.env)
        b = subprocess.Popen(command, env=self.env)
        self.assertEqual(sorted((a.wait(timeout=12), b.wait(timeout=12))), [0, 3])

    def test_matching_task_text_with_wrong_starttime_is_never_signalled(self):
        sentinel = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)', 'scope-test'])
        self.addCleanup(lambda: (sentinel.kill() if sentinel.poll() is None else None, sentinel.wait()))
        actual = scope.proc_info(sentinel.pid)
        fake = dict(actual, start=actual['start'] - 1)
        self.assertFalse(scope.signal_process(fake, signal.SIGKILL))
        self.assertIsNone(sentinel.poll())
        with mock.patch.object(scope, 'proc_info', return_value=dict(actual, start=actual['start'] + 1)), \
                mock.patch.object(scope.os, 'kill') as kill:
            self.assertFalse(scope.signal_process(actual, signal.SIGTERM))
            kill.assert_not_called()

    def test_old_boot_recovery_never_signals_saved_pid(self):
        data = {'boot': 'not-this-boot', 'token': 'f' * 32,
                'owner': {'pid': os.getpid(), 'start': 1},
                'members': [{'pid': os.getpid(), 'start': 1}]}
        with mock.patch.object(scope, 'signal_process') as signal_call:
            self.assertTrue(scope.recover(data))
            signal_call.assert_not_called()

    def test_forged_scope_marker_does_not_delete_other_work(self):
        sibling = self.module / 'cache/tasks/unrelated'
        sibling.mkdir(parents=True)
        (sibling / '.luoshu-task-owner').write_text('other-token')
        (sibling / 'keep').write_text('keep')
        scope.clear_workspaces({'token': 'requested-token', 'workspaces': [str(sibling)]})
        self.assertTrue((sibling / 'keep').exists())

    def test_tree_requires_original_birth_identity(self):
        sentinel = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
        self.addCleanup(lambda: (sentinel.kill() if sentinel.poll() is None else None, sentinel.wait()))
        actual = scope.proc_info(sentinel.pid)
        for value in ('', str(actual['start'] + 1)):
            args = types.SimpleNamespace(pid=sentinel.pid, start=value)
            self.assertEqual(scope.terminate_tree(args), 1)
            self.assertIsNone(sentinel.poll())

    def test_kernel_without_pidfd_still_reaps_through_owned_children(self):
        # Model an older Android kernel, not just missing Python wrappers. Only
        # our test copy changes; production has no environment bypass for this.
        helper = self.root / 'task_scope.py'
        helper.write_text(HELPER.read_text().replace('def pidfd_open(pid):\n',
                          "def pidfd_open(pid):\n    raise OSError(errno.ENOSYS, 'test kernel')\n"))
        self.helper = helper
        self.launch(self.orphan_code('no-pidfd'))
        self.assert_clean('no-pidfd')

    def test_switch_timeout_without_pidfd_does_not_wait_on_stuck_generator(self):
        common = self.module / 'common'
        common.mkdir()
        (common / 'background_task.sh').write_text((ROOT / 'common/background_task.sh').read_text())
        for name in ('font_switch_input.sh', 'font_switch_input.py', 'font_inventory_batch.py', 'font_coverage_fields.py'):
            (common / name).write_text((ROOT / 'common' / name).read_text())
        public = self.root / 'public'
        (public / 'fonts').mkdir(parents=True)
        (public / 'fonts/test-font.ttf').write_bytes(b'\0\1\0\0' + b'x' * 4096)
        helper = common / 'task_scope.py'
        helper.write_text(HELPER.read_text().replace('def pidfd_open(pid):\n',
                          "def pidfd_open(pid):\n    raise OSError(errno.ENOSYS, 'test kernel')\n"))
        binary = self.root / 'bin'
        binary.mkdir()
        # Accelerate only shell's elapsed-time fixture; the helper keeps real
        # monotonic deadlines and real Linux process signalling/reaping.
        sleep = binary / 'sleep'
        sleep.write_text('#!/bin/sh\nexec /bin/sleep 0.01\n')
        sleep.chmod(0o755)
        generator = self.root / 'generator.pid'
        manager = self.root / 'manager.sh'
        code = f"import os,time;from pathlib import Path;Path({str(generator)!r}).write_text(str(os.getpid()));time.sleep(60)"
        import shlex
        manager.write_text(f'#!/bin/sh\nexec {shlex.quote(sys.executable)} -c {shlex.quote(code)}\n')
        env = dict(self.env, LUOSHU_PUBLIC_DIR=str(public), LUOSHU_TASK_HELPER=str(helper), LUOSHU_FONT_MANAGER=str(manager),
                   LUOSHU_SWITCH_TIMEOUT_SECONDS='30', LUOSHU_TASK_TIMEOUT_SECONDS='60',
                   PATH=str(binary) + ':' + self.env['PATH'])
        started = subprocess.run(['sh', str(ROOT / 'common/font_switch_task.sh'), 'start', 'test-font'],
                                 env=env, text=True, capture_output=True, timeout=5)
        self.assertIn('"status":"ok"', started.stdout, started.stderr)
        pid = int(wait_for(lambda: scope.read(generator)))
        self.extra_pids.append(pid)
        wait_for(lambda: not Path(str(self.pidfile) + '.identity').exists(), timeout=25)
        self.assertFalse(alive(pid))
        self.assertIn('超过 30 秒', scope.read(self.config / 'switch_task.conf'))

    def test_old_boot_identity_reclaims_only_marked_workspace_without_signalling(self):
        token = 'a' * 32
        workspace = self.module / 'cache/tasks' / token
        workspace.mkdir(parents=True)
        (workspace / '.luoshu-task-owner').write_text(token)
        (workspace / 'interrupted-input.ttf').write_text('synthetic bytes')
        unowned = self.module / 'cache/tasks/unowned'
        unowned.mkdir()
        (unowned / '.luoshu-task-owner').write_text('different-token')
        data = {'version': 1, 'task': 'previous-boot', 'token': token,
                'boot': 'previous-boot-id', 'owner': scope.proc_info(os.getpid()),
                'members': [scope.proc_info(os.getpid())],
                'workspaces': [str(workspace), str(unowned)]}
        scope.atomic_write(str(self.pidfile) + '.identity', json.dumps(data))
        scope.atomic_write(str(self.pidfile) + '.scope', token)
        loaded = scope.load_identity(self.pidfile)
        self.assertEqual(data, loaded)
        with mock.patch.object(scope, 'signal_process') as signal_process, \
                mock.patch.object(scope, 'same_process', return_value=True) as same_process:
            self.assertFalse(scope.identity_alive(loaded))
            self.assertEqual(0, scope.reconcile(types.SimpleNamespace(pidfile=self.pidfile)))
            signal_process.assert_not_called()
            same_process.assert_not_called()
        self.assertFalse(workspace.exists())
        self.assertTrue(unowned.exists())
        self.assertFalse(Path(str(self.pidfile) + '.identity').exists())

    def test_kernel_without_pidfd_refuses_nonchild_signal(self):
        # PID 1 is excluded separately; use our own parent to test the ownership
        # check. waitid must report ECHILD, and no numeric kill may occur.
        parent = scope.proc_info(os.getppid())
        with mock.patch.object(scope, 'pidfd_open', side_effect=OSError(errno.ENOSYS, 'old kernel')), \
                mock.patch.object(scope.os, 'kill') as kill:
            self.assertFalse(scope.signal_process(parent, signal.SIGTERM))
            kill.assert_not_called()

    @unittest.skipUnless(os.uname().machine in ('aarch64', 'arm64', 'x86_64'), 'syscall ABI')
    def test_ctypes_pidfd_backend_when_python_wrappers_are_missing(self):
        no_wrappers = types.SimpleNamespace(uname=os.uname)
        with mock.patch.object(scope, 'os', no_wrappers), \
                mock.patch.object(scope, 'signal', types.SimpleNamespace()):
            fd = scope.pidfd_open(os.getpid())
            try:
                scope.pidfd_send(fd, 0)
            finally:
                os.close(fd)

    def test_task_inherits_mount_namespace_without_unshare(self):
        destination = self.root / 'mount-namespace'
        code = f"import os; from pathlib import Path; Path({str(destination)!r}).write_text(os.readlink('/proc/self/ns/mnt'))"
        self.launch(code)
        self.assertEqual(wait_for(lambda: scope.read(destination)), os.readlink('/proc/self/ns/mnt'))
        wait_for(lambda: not Path(str(self.pidfile) + '.identity').exists())

    def test_fixed_mix_commit_monitor_finishes_before_scope_cleanup(self):
        self.env['LUOSHU_MIX_REQUEST_ID'] = 'request-commit-test'
        pidfile = self.config / 'axes_worker.pid'
        taskdir = self.module / 'cache/axes-mix/scope-test'
        taskdir.mkdir(parents=True)
        taskfile = self.config / 'axes_task.conf'
        taskfile.write_text(f'task=scope-test\nstate=running\nroot={taskdir}\nchildTask=inner\n')
        final = self.config / 'mix-finalize-state.conf'
        code = f"""
import os, time
from pathlib import Path
if os.fork() == 0:
    time.sleep(.4)
    Path({str(final)!r}).write_text('state=success\\nrequestId=request-commit-test\\n')
    os._exit(0)
p = Path({str(taskfile)!r})
p.write_text(p.read_text().replace('state=running', 'state=success'))
"""
        self.launch(code, pidfile=pidfile)
        wait_for(lambda: not Path(str(pidfile) + '.identity').exists())
        self.assertIn('state=success', scope.read(final))
        self.assertIn('state=success', scope.read(taskfile))
        self.assertFalse(taskdir.exists())

    def test_submission_serializes_before_any_stage_mutation(self):
        calls = self.root / 'stage-creations'
        code = f"import time; from pathlib import Path; p=Path({str(calls)!r}); p.write_text('one'); time.sleep(.6); print('accepted')"
        command = [sys.executable, str(HELPER), 'submit', str(self.config), '--',
                   sys.executable, '-c', code]
        first = subprocess.Popen(command, stdout=subprocess.PIPE, env=self.env)
        wait_for(lambda: calls.exists())
        second = subprocess.run(command, text=True, capture_output=True, env=self.env, timeout=5)
        self.assertIn('正在启动', second.stdout)
        self.assertEqual(first.communicate(timeout=5)[0].strip(), b'accepted')

    def test_shell_requires_birth_sidecar_even_if_task_and_boot_match(self):
        self.launch('import time; time.sleep(30)')
        start = Path(str(self.pidfile) + '.start')
        valid = start.read_text()
        command = ['sh', '-c', '. "$1"; luoshu_task_pid_alive "$2" scope-test',
                   'sh', str(ROOT / 'common/background_task.sh'), str(self.pidfile)]
        self.assertEqual(subprocess.run(command, env=self.env).returncode, 0)
        start.write_text(str(int(valid) + 1))
        self.assertNotEqual(subprocess.run(command, env=self.env).returncode, 0)
        start.unlink()
        self.assertNotEqual(subprocess.run(command, env=self.env).returncode, 0)
        start.write_text(valid)


if __name__ == '__main__':
    unittest.main()
