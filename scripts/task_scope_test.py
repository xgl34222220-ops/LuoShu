#!/usr/bin/env python3
"""Real process/namespace tests, including escaped sessions and late forks."""
import json
import ctypes
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
PROGRAM = ROOT / 'common/task_scope.py'


class TaskScopeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.env = dict(os.environ, LUOSHU_TMP_DIR=str(self.directory / 'tmp'))
        for name in ('LUOSHU_TASK_SCOPE_PID', 'LUOSHU_TASK_SCOPE_PIDFILE',
                     'LUOSHU_SCOPE_ALLOW_HANDOFF', 'LUOSHU_SCOPE_HANDOFF'):
            self.env.pop(name, None)
        self.pidfile = self.directory / 'scope.pid'
        self.fixture = self.directory / 'worker.py'
        self.fixture.write_text('''import json, os, signal, sys, time
from pathlib import Path
directory = Path(sys.argv[1]); mode = sys.argv[2]
def publish(name):
    (directory / (name + '.json')).write_text(json.dumps({'pid': os.getpid(), 'proc': os.readlink('/proc/self')}))
def leaf(name):
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    publish(name)
    while True: time.sleep(.02)
if os.fork() == 0: leaf('normal')
if os.fork() == 0:
    os.setsid()
    if os.fork() != 0: os._exit(0)
    leaf('escaped')
if os.fork() == 0:
    fired = False
    def late(number, frame):
        global fired
        if not fired:
            fired = True
            if os.fork() == 0:
                os.setsid(); leaf('late')
    signal.signal(signal.SIGTERM, late)
    publish('forker')
    while True: time.sleep(.02)
while not all((directory / (n + '.json')).exists() for n in ('normal','escaped','forker')): time.sleep(.01)
Path(os.environ['LUOSHU_TASK_SCOPE_TMPDIR'], 'owned.tmp').write_text('temporary')
if mode == 'success': sys.exit(0)
if mode == 'failure': sys.exit(7)
while True: time.sleep(.02)
''')
        self.sentinel = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
        self.addCleanup(self.dispose, self.sentinel)

    @staticmethod
    def dispose(process):
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=6)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=2)

    def wait_for(self, condition):
        end = time.monotonic() + 5
        while time.monotonic() < end:
            if condition():
                return
            time.sleep(.02)
        self.fail('condition did not become true')

    def start(self, mode='hold', timeout=5, extra=()):
        process = subprocess.Popen([sys.executable, str(PROGRAM), 'run', '--pid-file', str(self.pidfile),
                                    '--task', 'owned-task', '--timeout', str(timeout), *extra, '--',
                                    sys.executable, str(self.fixture), str(self.directory), mode],
                                   env=self.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(self.dispose, process)
        self.wait_for(lambda: (self.directory / 'escaped.json').exists())
        return process

    def assert_clean(self, process, result):
        self.assertEqual(process.wait(timeout=7), result)
        proof = json.loads(Path(str(self.pidfile) + '.cleanup.json').read_text())
        self.assertTrue(proof['cleaned'])
        self.assertEqual(proof['leftoverPids'], [])
        self.assertGreaterEqual(proof['reaped'], 3)
        self.assertFalse(self.pidfile.exists())
        self.assertFalse(list((self.directory / 'tmp').glob('task-*')))
        for name in ('normal', 'escaped', 'forker', 'late'):
            path = self.directory / (name + '.json')
            if path.exists():
                record = json.loads(path.read_text())
                self.assertFalse(Path('/proc', record['proc']).exists(), name + ' was not reaped')
        self.assertIsNone(self.sentinel.poll(), 'unrelated sentinel was killed')

    def test_success_reclaims_double_fork_setsid_term_ignoring_children(self):
        self.assert_clean(self.start('success'), 0)

    def test_failure_reclaims_owned_children(self):
        self.assert_clean(self.start('failure'), 7)

    def test_timeout_reclaims_owned_children(self):
        started = time.monotonic()
        self.assert_clean(self.start(timeout=.3), 124)
        self.assertLess(time.monotonic() - started, 5)

    def test_cancel_waits_for_reaping_and_late_fork(self):
        process = self.start()
        result = subprocess.run([sys.executable, str(PROGRAM), 'cancel', str(self.pidfile), 'owned-task'],
                                env=self.env, capture_output=True, text=True, timeout=7)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)['data']['cleaned'])
        self.assert_clean(process, 143)
        self.assertTrue((self.directory / 'late.json').exists())

    def test_wrong_task_cannot_cancel_scope(self):
        process = self.start()
        result = subprocess.run([sys.executable, str(PROGRAM), 'cancel', str(self.pidfile), 'other-task'],
                                env=self.env, capture_output=True, text=True, timeout=2)
        self.assertEqual(result.returncode, 3)
        self.assertIsNone(process.poll())
        process.terminate(); self.assert_clean(process, 143)

    def test_changed_start_time_and_boot_cannot_signal_reused_pid(self):
        # Use an unrelated process with the task string in its command line.
        sentinel_proc = None
        for entry in Path('/proc').iterdir():
            if entry.name.isdigit():
                try:
                    lines = (entry / 'status').read_text().splitlines()
                    if any(line.startswith('NSpid:') and int(line.split()[-1]) == self.sentinel.pid for line in lines):
                        if os.readlink(entry / 'ns/pid') == os.readlink('/proc/self/ns/pid'):
                            sentinel_proc = entry
                            break
                except (OSError, ValueError):
                    pass
        self.assertIsNotNone(sentinel_proc)
        fields = (sentinel_proc / 'stat').read_text().rsplit(') ', 1)[1].split()
        record = {'pid': self.sentinel.pid, 'procPid': int(sentinel_proc.name), 'start': fields[19] + '0',
                  'boot': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                  'namespace': os.readlink('/proc/self/ns/pid'), 'task': 'owned-task'}
        for bad in ('start', 'boot'):
            if bad == 'boot':
                record['start'] = fields[19]; record['boot'] = 'previous-boot'
            Path(str(self.pidfile) + '.owner.json').write_text(json.dumps(record))
            for suffix, key in (('', 'pid'), ('.task', 'task'), ('.start', 'start'), ('.boot', 'boot')):
                Path(str(self.pidfile) + suffix).write_text(str(record[key]))
            subprocess.run([sys.executable, str(PROGRAM), 'cancel', str(self.pidfile), 'owned-task'],
                           capture_output=True, text=True, timeout=2)
            self.assertIsNone(self.sentinel.poll())

    def test_parent_disconnect_reclaims_children(self):
        ctypes.CDLL(None).prctl(36, 1, 0, 0, 0)
        launcher = self.directory / 'launcher.py'
        launcher.write_text('''import subprocess, sys, time
from pathlib import Path
process = subprocess.Popen(sys.argv[1:])
while not Path(sys.argv[1:][sys.argv[1:].index('--pid-file') + 1] + '.ready').exists(): time.sleep(.01)
Path(''' + repr(str(self.directory / 'parent.ready')) + ''').write_text(str(process.pid))
time.sleep(60)
''')
        parent = subprocess.Popen([sys.executable, str(launcher), sys.executable, str(PROGRAM), 'run',
                                   '--pid-file', str(self.pidfile), '--task', 'owned-task', '--timeout', '5',
                                   '--parent-watch', '--', sys.executable, str(self.fixture), str(self.directory), 'hold'],
                                  env=self.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(self.dispose, parent)
        self.wait_for(lambda: (self.directory / 'escaped.json').exists())
        parent.kill(); parent.wait()
        self.wait_for(lambda: Path(str(self.pidfile) + '.cleanup.json').exists())
        proof = json.loads(Path(str(self.pidfile) + '.cleanup.json').read_text())
        self.assertEqual(proof['reason'], 'parent-exited')
        self.assertTrue(proof['cleaned'])
        self.assertFalse(self.pidfile.exists())
        self.assertIsNone(self.sentinel.poll())
        supervisor_pid = int((self.directory / 'parent.ready').read_text())
        self.wait_for(lambda: os.waitpid(supervisor_pid, os.WNOHANG)[0] == supervisor_pid)

    def test_reused_task_id_cannot_accept_old_cleanup_after_supervisor_kill(self):
        ctypes.CDLL(None).prctl(36, 1, 0, 0, 0)
        previous = subprocess.run([sys.executable, str(PROGRAM), 'run', '--pid-file', str(self.pidfile),
                                   '--task', 'same-task', '--timeout', '5', '--', 'sh', '-c', 'exit 0'],
                                  env=self.env, capture_output=True, text=True, timeout=7)
        self.assertEqual(previous.returncode, 0)
        old_proof = Path(str(self.pidfile) + '.cleanup.json').read_text()
        child_file = self.directory / 'child.pid'
        worker = "import os,time; from pathlib import Path; Path(" + repr(str(child_file)) + ").write_text(str(os.getpid())); time.sleep(60)"
        current = subprocess.Popen([sys.executable, str(PROGRAM), 'run', '--pid-file', str(self.pidfile),
                                    '--task', 'same-task', '--timeout', '5', '--', sys.executable, '-c', worker],
                                   env=self.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(self.dispose, current)
        self.wait_for(lambda: child_file.exists())
        Path(str(self.pidfile) + '.cleanup.json').write_text(old_proof)
        current.kill(); current.wait(timeout=2)
        result = subprocess.run([sys.executable, str(PROGRAM), 'cancel', str(self.pidfile), 'same-task'],
                                env=self.env, capture_output=True, text=True, timeout=2)
        self.assertEqual(result.returncode, 125)
        self.assertFalse(json.loads(result.stdout)['data']['cleaned'])
        self.assertTrue(Path(str(self.pidfile) + '.owner.json').exists())
        child = int(child_file.read_text())
        os.kill(child, signal.SIGKILL)
        self.wait_for(lambda: os.waitpid(child, os.WNOHANG)[0] == child)
        self.assertIsNone(self.sentinel.poll())

    def test_temporary_cleanup_exception_preserves_owner_and_writes_failure_proof(self):
        injection = """import importlib.util, sys
spec=importlib.util.spec_from_file_location('scope', sys.argv[1]); scope=importlib.util.module_from_spec(spec); spec.loader.exec_module(scope)
def fail(record): raise OSError('fixture removal failed')
scope.remove_temporary=fail
sys.argv=sys.argv[1:]
sys.exit(scope.main())
"""
        process = subprocess.run([sys.executable, '-c', injection, str(PROGRAM), 'run', '--pid-file', str(self.pidfile),
                                  '--task', 'cleanup-failure', '--timeout', '5', '--', sys.executable, str(self.fixture),
                                  str(self.directory), 'success'], env=self.env, capture_output=True, text=True, timeout=7)
        self.assertEqual(process.returncode, 125, process.stderr)
        proof = json.loads(Path(str(self.pidfile) + '.cleanup.json').read_text())
        self.assertFalse(proof['cleaned'])
        self.assertEqual(proof['leftoverPids'], [])
        self.assertIn('fixture removal failed', proof['cleanupErrors'])
        self.assertTrue(Path(str(self.pidfile) + '.owner.json').exists())
        self.assertIsNone(self.sentinel.poll())

    def test_module_cancel_preserves_unrelated_process_and_does_not_create_old_state(self):
        module = self.directory / 'old-module'
        common = module / 'common'; common.mkdir(parents=True)
        config = module / 'config'; config.mkdir()
        manager = common / 'legacy-manager.sh'
        # Keep the module script in the exact command argv for old-version proof.
        manager.write_text('#!/bin/sh\n' + sys.executable + ' ' + str(self.fixture) + ' ' +
                           str(self.directory) + ' hold &\nwait $!\n')
        legacy_temporary = self.directory / 'legacy-tmp'; legacy_temporary.mkdir()
        ctypes.CDLL(None).prctl(36, 1, 0, 0, 0)
        legacy = subprocess.Popen(['sh', str(manager), 'legacy-task'], stdout=subprocess.DEVNULL,
                                  stderr=subprocess.DEVNULL, env=dict(self.env, LUOSHU_TASK_SCOPE_TMPDIR=str(legacy_temporary)))
        self.addCleanup(self.dispose, legacy)
        self.wait_for(lambda: (self.directory / 'escaped.json').exists())
        self.wait_for(lambda: (self.directory / 'forker.json').exists())
        # Deliberately use a simpler rooted job for the migration proof: an old
        # version cannot identify its already reparented double-fork orphan.
        escaped = json.loads((self.directory / 'escaped.json').read_text())
        os.kill(escaped['pid'], signal.SIGKILL)
        self.wait_for(lambda: os.waitpid(escaped['pid'], os.WNOHANG)[0] == escaped['pid'])
        pidfile = config / 'axes_worker.pid'
        pidfile.write_text(str(legacy.pid))
        Path(str(pidfile) + '.task').write_text('legacy-task')
        Path(str(pidfile) + '.boot').write_text(Path('/proc/sys/kernel/random/boot_id').read_text())
        result = subprocess.run([sys.executable, str(PROGRAM), 'cancel-all', str(module)],
                                env=self.env, capture_output=True, text=True, timeout=7)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIsNone(self.sentinel.poll())
        legacy.wait(timeout=2)
        self.assertFalse(pidfile.exists())
        self.assertFalse((module / '.luoshu-state').exists())
        for name in ('normal', 'forker', 'late'):
            path = self.directory / (name + '.json')
            if path.exists():
                child = json.loads(path.read_text()); pid = child['pid']
                try:
                    end = time.monotonic() + 2
                    finished = False
                    while time.monotonic() < end:
                        if os.waitpid(pid, os.WNOHANG)[0] == pid:
                            finished = True; break
                        time.sleep(.02)
                    if not finished:
                        os.kill(pid, signal.SIGKILL)
                        self.wait_for(lambda: os.waitpid(pid, os.WNOHANG)[0] == pid)
                    self.assertTrue(finished, 'legacy adapter missed owned child ' + name + ': ' + result.stdout)
                except ChildProcessError:
                    self.assertFalse(Path('/proc', child['proc']).exists())

    def test_font_switch_success_failure_and_cancel_wait_for_child_cleanup(self):
        module = self.directory / 'module'; common = module / 'common'; common.mkdir(parents=True)
        (module / 'module.prop').write_text('id=LuoShu\n')
        for name in ('task_scope.sh', 'task_scope.py', 'background_task.sh', 'runtime_paths.sh', 'runtime_paths_lock.py'):
            (common / name).symlink_to(ROOT / 'common' / name)
        manager = self.directory / 'manager.sh'
        manager.write_text('#!/bin/sh\nprintf \'{"status":"ok"}\\n\'\n' +
                           'exec ' + sys.executable + ' ' + str(self.fixture) + ' ' + str(self.directory) + ' "$3"\n')
        env = dict(self.env, MODDIR=str(module), LUOSHU_TASK_SCOPE_PYTHON=sys.executable,
                   LUOSHU_RUNTIME_PATHS_PYTHON=sys.executable, LUOSHU_FONT_MANAGER=str(manager))
        task_script = ROOT / 'common/font_switch_task.sh'
        for mode in ('success', 'failure', 'hold'):
            for path in self.directory.glob('*.json'):
                path.unlink()
            response = subprocess.run(['sh', str(common / 'task_scope.sh'), 'request-run', 'switch-' + mode,
                                       '5', '--', 'sh', str(task_script), 'start', mode], env=env,
                                      capture_output=True, text=True, timeout=7)
            self.assertEqual(response.returncode, 0, response.stderr)
            task = json.loads(response.stdout)['data']['task']
            worker = module / '.luoshu-state/tasks/switch_task_worker.pid'
            if mode == 'hold':
                self.wait_for(lambda: (self.directory / 'escaped.json').exists())
                cancellation = subprocess.run(['sh', str(task_script), 'cancel', task], env=env,
                                              capture_output=True, text=True, timeout=7)
                self.assertEqual(cancellation.returncode, 0, cancellation.stderr)
                self.assertTrue(json.loads(cancellation.stdout)['data']['cleaned'])
            self.wait_for(lambda: Path(str(worker) + '.cleanup.json').exists() and not worker.exists())
            state = (module / 'config/switch_task.conf').read_text()
            self.assertIn('state=' + ('success' if mode == 'success' else 'failed') + '\n', state)
            self.assertFalse(list((module / '.luoshu-state/tmp').iterdir()))
            for name in ('normal', 'escaped', 'forker', 'late'):
                path = self.directory / (name + '.json')
                if path.exists():
                    self.assertFalse(Path('/proc', json.loads(path.read_text())['proc']).exists())
            self.assertIsNone(self.sentinel.poll())


if __name__ == '__main__':
    unittest.main()
