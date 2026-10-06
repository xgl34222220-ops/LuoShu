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
                record['start'] = fields[19]; record['boot'] = '00000000-0000-4000-8000-000000000001'
            Path(str(self.pidfile) + '.owner.json').write_text(json.dumps(record))
            for suffix, key in (('', 'pid'), ('.task', 'task'), ('.start', 'start'), ('.boot', 'boot')):
                Path(str(self.pidfile) + suffix).write_text(str(record[key]))
            subprocess.run([sys.executable, str(PROGRAM), 'cancel', str(self.pidfile), 'owned-task'],
                           capture_output=True, text=True, timeout=2)
            self.assertIsNone(self.sentinel.poll())
        record.update(start=fields[19], boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip(), namespace='pid:[different]')
        Path(str(self.pidfile) + '.owner.json').write_text(json.dumps(record))
        for suffix, key in (('', 'pid'), ('.task', 'task'), ('.start', 'start'), ('.boot', 'boot')):
            Path(str(self.pidfile) + suffix).write_text(str(record[key]))
        proof = dict(schema='task-cleanup-v2', cleaned=True, leftoverPids=[], cleanupErrors=[],
                     namespace=os.readlink('/proc/self/ns/pid'),
                     **{key: record[key] for key in ('task', 'pid', 'start', 'boot')})
        Path(str(self.pidfile) + '.cleanup.json').write_text(json.dumps(proof))
        wrong_namespace = subprocess.run([sys.executable, str(PROGRAM), 'cancel', str(self.pidfile), 'owned-task'],
                                         capture_output=True, text=True, timeout=2)
        self.assertEqual(wrong_namespace.returncode, 125)
        self.assertTrue(Path(str(self.pidfile) + '.owner.json').exists())
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

    def test_dead_supervisor_cannot_be_replaced_with_unproved_live_child(self):
        ctypes.CDLL(None).prctl(36, 1, 0, 0, 0)
        child_file = self.directory / 'unproved-child.json'
        worker = ("import json,os,time; from pathlib import Path; "
                  "p=Path('/proc/self/stat'); start=p.read_text().rsplit(') ',1)[1].split()[19]; "
                  "Path(" + repr(str(child_file)) + ").write_text(json.dumps({'pid':os.getpid(),"
                  "'proc':os.readlink('/proc/self'),'start':start})); time.sleep(60)")
        supervisor = subprocess.Popen([sys.executable, str(PROGRAM), 'run', '--pid-file', str(self.pidfile),
                                       '--task', 'unproved-task', '--timeout', '30', '--', sys.executable, '-c', worker],
                                      env=self.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(self.dispose, supervisor)
        self.wait_for(child_file.exists)
        child = json.loads(child_file.read_text())

        def dispose_child():
            try:
                fields = Path('/proc', child['proc'], 'stat').read_text().rsplit(') ', 1)[1].split()
                if fields[19] == child['start']:
                    os.kill(child['pid'], signal.SIGKILL)
                os.waitpid(child['pid'], 0)
            except (FileNotFoundError, ProcessLookupError, ChildProcessError):
                pass
        self.addCleanup(dispose_child)
        supervisor.kill(); supervisor.wait(timeout=2)
        owner_path = Path(str(self.pidfile) + '.owner.json')
        owner = json.loads(owner_path.read_text())
        proof_path = Path(str(self.pidfile) + '.cleanup.json')
        proof_path.write_text(json.dumps(dict(schema='task-cleanup-v2', cleaned=False,
                                             leftoverPids=[child['pid']], cleanupErrors=[],
                                             **{key: owner[key] for key in ('task', 'pid', 'start', 'boot')})))
        evidence = {suffix: Path(str(self.pidfile) + suffix).read_bytes()
                    for suffix in ('', '.owner.json', '.task', '.start', '.boot', '.cleanup.json')}
        marker = self.directory / 'replacement-started'
        replacement = subprocess.run([sys.executable, str(PROGRAM), 'run', '--pid-file', str(self.pidfile),
                                      '--task', 'replacement-task', '--timeout', '5', '--', 'touch', str(marker)],
                                     env=self.env, capture_output=True, text=True, timeout=3)
        self.assertEqual(replacement.returncode, 125, replacement.stderr)
        self.assertFalse(marker.exists())
        inspection = subprocess.run([sys.executable, str(PROGRAM), 'settled', str(self.pidfile)],
                                    env=self.env, capture_output=True, text=True, timeout=3)
        self.assertEqual(inspection.returncode, 125)

        module = self.directory / 'launcher-module'; common = module / 'common'; common.mkdir(parents=True)
        (module / 'module.prop').write_text('id=LuoShu\n')
        for name in ('task_scope.sh', 'task_scope.py', 'runtime_paths.sh', 'runtime_paths_lock.py'):
            (common / name).symlink_to(ROOT / 'common' / name)
        launch_env = dict(self.env, MODDIR=str(module), LUOSHU_TASK_SCOPE_PYTHON=sys.executable,
                          LUOSHU_RUNTIME_PATHS_PYTHON=sys.executable)
        detached = subprocess.run(['sh', '-c', '. "$1"; luoshu_start_detached "$2" replacement-task "$3" touch "$4"',
                                   'sh', str(ROOT / 'common/background_task.sh'), str(self.pidfile),
                                   str(self.directory / 'replacement.log'), str(marker)],
                                  env=launch_env, capture_output=True, text=True, timeout=3)
        self.assertEqual(detached.returncode, 125, detached.stderr)
        self.assertFalse(marker.exists())
        for suffix, before in evidence.items():
            self.assertEqual(Path(str(self.pidfile) + suffix).read_bytes(), before, suffix + ' was overwritten')
        self.assertTrue(Path('/proc', child['proc']).exists())
        self.assertIsNone(self.sentinel.poll())

    def test_sequential_scope_reuse_accepts_cleaned_slots_and_previous_boot(self):
        for task in ('first-task', 'second-task', 'third-task'):
            result = subprocess.run([sys.executable, str(PROGRAM), 'run', '--pid-file', str(self.pidfile),
                                     '--task', task, '--timeout', '5', '--', 'sh', '-c', 'exit 0'],
                                    env=self.env, capture_output=True, text=True, timeout=3)
            self.assertEqual(result.returncode, 0, result.stderr)
            proof = json.loads(Path(str(self.pidfile) + '.cleanup.json').read_text())
            self.assertEqual(proof['task'], task)
            self.assertTrue(proof['cleaned'])
        record = dict(task='previous-boot-task', pid=123, procPid=123, start='456',
                      namespace=os.readlink('/proc/self/ns/pid'), boot='00000000-0000-4000-8000-000000000001')
        for suffix, key in (('', 'pid'), ('.task', 'task'), ('.start', 'start'), ('.boot', 'boot')):
            Path(str(self.pidfile) + suffix).write_text(str(record[key]))
        Path(str(self.pidfile) + '.owner.json').write_text(json.dumps(record))
        Path(str(self.pidfile) + '.cleanup.json').unlink()
        result = subprocess.run([sys.executable, str(PROGRAM), 'run', '--pid-file', str(self.pidfile),
                                 '--task', 'new-boot-task', '--timeout', '5', '--', 'sh', '-c', 'exit 0'],
                                env=self.env, capture_output=True, text=True, timeout=3)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(Path(str(self.pidfile) + '.cleanup.json').read_text())['cleaned'])
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
        evidence = {suffix: Path(str(self.pidfile) + suffix).read_bytes()
                    for suffix in ('', '.owner.json', '.cleanup.json')}
        retry = subprocess.run([sys.executable, str(PROGRAM), 'run', '--pid-file', str(self.pidfile),
                                '--task', 'must-not-replace-failed-cleanup', '--timeout', '5', '--', 'sh', '-c', 'exit 0'],
                               env=self.env, capture_output=True, text=True, timeout=3)
        self.assertEqual(retry.returncode, 125, retry.stderr)
        for suffix, before in evidence.items():
            self.assertEqual(Path(str(self.pidfile) + suffix).read_bytes(), before)
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

    def font_module(self):
        module = self.directory / 'font-module'; common = module / 'common'; common.mkdir(parents=True)
        (module / 'module.prop').write_text('id=LuoShu\n')
        for name in ('task_scope.sh', 'task_scope.py', 'background_task.sh', 'runtime_paths.sh', 'runtime_paths_lock.py'):
            (common / name).symlink_to(ROOT / 'common' / name)
        manager = self.directory / 'font-manager.sh'
        manager.write_text('#!/bin/sh\n' +
                           'printf "%s\\n" "$LUOSHU_SWITCH_REQUEST_ID" > "$MODDIR/config/seen-request-id"\n' +
                           'printf "state=mounted\\nfont=%s\\nrequestId=%s\\nbootId=%s\\n" "$3" "$LUOSHU_SWITCH_REQUEST_ID" "$(cat /proc/sys/kernel/random/boot_id)" > "$MODDIR/config/font-live.conf"\n' +
                           'printf "font=%s\\nrequestId=%s\\n" "$3" "$LUOSHU_SWITCH_REQUEST_ID" > "$MODDIR/config/font-payload-next.conf"\n' +
                           'printf "state=mounted\\n" > "$MODDIR/config/self-mount.conf"\n' +
                           'printf \'{"status":"ok","data":{"liveApplied":true,"activation":"live-mounted"}}\\n\'\n')
        env = dict(self.env, MODDIR=str(module), LUOSHU_TASK_SCOPE_PYTHON=sys.executable,
                   LUOSHU_RUNTIME_PATHS_PYTHON=sys.executable, LUOSHU_FONT_MANAGER=str(manager))
        return module, env

    def test_font_terminal_write_waits_for_supervisor_cleanup_failure(self):
        module, env = self.font_module()
        pidfile = module / '.luoshu-state/tasks/switch_task_worker.pid'
        injection = """import importlib.util, sys
spec=importlib.util.spec_from_file_location('scope', sys.argv[1]); scope=importlib.util.module_from_spec(spec); spec.loader.exec_module(scope)
def fail(record): raise OSError('fixture root cleanup failed')
scope.remove_temporary=fail
sys.argv=sys.argv[1:]
sys.exit(scope.main())
"""
        run = subprocess.run([sys.executable, '-c', injection, str(PROGRAM), 'run', '--pid-file', str(pidfile),
                              '--task', 'font-proof-failure', '--timeout', '5', '--',
                              'sh', str(ROOT / 'common/font_switch_task.sh'), 'run', 'font-proof-failure', 'custom', '1'],
                             env=env, capture_output=True, text=True, timeout=7)
        self.assertEqual(run.returncode, 125, run.stderr)
        proof_before = Path(str(pidfile) + '.cleanup.json').read_bytes()
        for action, argument in (('status', 'font-proof-failure'), ('start', 'other-font'), ('cancel', 'font-proof-failure')):
            result = subprocess.run(['sh', str(ROOT / 'common/font_switch_task.sh'), action, argument],
                                    env=env, capture_output=True, text=True, timeout=3)
            response = json.loads(result.stdout)
            if action == 'status':
                self.assertEqual(response['data']['state'], 'cleanup-pending')
            elif action == 'start':
                self.assertEqual(response['status'], 'error')
            else:
                self.assertEqual(result.returncode, 125)
                self.assertFalse(response['data']['cleaned'])
        state = (module / 'config/switch_task.conf').read_text()
        self.assertIn('task=font-proof-failure\n', state)
        self.assertIn('state=cleanup-pending\n', state)
        self.assertIn('terminalState=success\n', state)
        self.assertEqual(Path(str(pidfile) + '.cleanup.json').read_bytes(), proof_before)
        self.assertTrue(Path(str(pidfile) + '.owner.json').exists())
        self.assertIsNone(self.sentinel.poll())

    def test_font_live_journal_blocks_success_and_cancel_until_bounded_recovery(self):
        module, env = self.font_module()
        pidfile = module / '.luoshu-state/tasks/switch_task_worker.pid'
        script = ROOT / 'common/font_switch_task.sh'
        task = 'font-live-proof'
        run = subprocess.run([sys.executable, str(PROGRAM), 'run', '--pid-file', str(pidfile), '--task', task,
                              '--timeout', '5', '--', 'sh', str(script), 'run', task, 'custom', '1'],
                             env=env, capture_output=True, text=True, timeout=7)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual((module / 'config/seen-request-id').read_text().strip(), task)
        status = subprocess.run(['sh', str(script), 'status', task], env=env, capture_output=True, text=True, timeout=3)
        data = json.loads(status.stdout)['data']
        self.assertEqual(data['state'], 'success')
        self.assertTrue(data['liveApplied'])
        self.assertEqual(data['activation'], 'live-mounted')
        (module / 'config/self-mount.conf').write_text('state=failed\n')
        stale = subprocess.run(['sh', str(script), 'status', task], env=env, capture_output=True, text=True, timeout=3)
        self.assertFalse(json.loads(stale.stdout)['data']['liveApplied'])
        (module / 'config/self-mount.conf').write_text('state=mounted\n')
        next_journal = module / '.luoshu-state/backup/next-transaction'
        next_journal.mkdir(); (next_journal / 'journal.conf').write_text('pending\n')
        selection_pending = subprocess.run(['sh', str(script), 'status', task], env=env, capture_output=True, text=True, timeout=3)
        self.assertEqual(json.loads(selection_pending.stdout)['data']['state'], 'cleanup-pending')
        journal = module / 'config/font-live-transaction.conf'; journal.write_text('pending\n')
        helper = module / 'common/font_live_switch.sh'
        helper.write_text('#!/bin/sh\n[ "$1" = recover ] || exit 1\n' +
                          '[ -f "$MODDIR/config/recovery-enabled" ] || exit 1\n' +
                          'rm -f "$MODDIR/config/font-live-transaction.conf"\n' +
                          'rm -rf "$MODDIR/.luoshu-state/backup/next-transaction"\n')
        status = subprocess.run(['sh', str(script), 'status', task], env=env, capture_output=True, text=True, timeout=3)
        data = json.loads(status.stdout)['data']
        self.assertEqual(data['state'], 'cleanup-pending')
        self.assertFalse(data['liveApplied'])
        cancel = subprocess.run(['sh', str(script), 'cancel', task], env=env, capture_output=True, text=True, timeout=3)
        self.assertEqual(cancel.returncode, 125, cancel.stderr)
        self.assertFalse(json.loads(cancel.stdout)['data']['cleaned'])
        self.assertTrue(journal.exists())
        start = subprocess.run(['sh', str(script), 'start', 'other-font'], env=env, capture_output=True, text=True, timeout=3)
        self.assertEqual(json.loads(start.stdout)['status'], 'error')
        self.assertIn('task=' + task + '\n', (module / 'config/switch_task.conf').read_text())
        (module / 'config/recovery-enabled').touch()
        retry = subprocess.run(['sh', str(script), 'cancel', task], env=env, capture_output=True, text=True, timeout=3)
        self.assertEqual(retry.returncode, 0, retry.stderr)
        self.assertTrue(json.loads(retry.stdout)['data']['cleaned'])
        self.assertFalse(journal.exists())
        self.assertFalse(next_journal.exists())
        self.assertIn('state=failed\n', (module / 'config/switch_task.conf').read_text())
        next_run = subprocess.run(['sh', str(script), 'start', 'next-font'], env=env, capture_output=True, text=True, timeout=3)
        self.assertEqual(json.loads(next_run.stdout)['status'], 'ok', next_run.stderr)
        next_task = json.loads(next_run.stdout)['data']['task']
        self.wait_for(lambda: Path(str(pidfile) + '.cleanup.json').exists() and
                      json.loads(Path(str(pidfile) + '.cleanup.json').read_text()).get('task') == next_task)
        status = subprocess.run(['sh', str(script), 'status', next_task], env=env, capture_output=True, text=True, timeout=3)
        self.assertEqual(json.loads(status.stdout)['data']['state'], 'success')
        for proof in (module / '.luoshu-state/tasks').glob('*.cleanup.json'):
            self.assertTrue(json.loads(proof.read_text())['cleaned'], str(proof))
        self.assertFalse(list((module / '.luoshu-state/tasks').glob('*.pid')))
        self.assertFalse(list((module / '.luoshu-state/tmp').iterdir()))
        self.assertIsNone(self.sentinel.poll())

    def test_mix_terminal_waits_for_all_slot_proofs_and_preserves_unknown_owner(self):
        module, env = self.font_module()
        for name in ('font_next_transaction.sh', 'font_switch_lock.sh'):
            (module / 'common' / name).symlink_to(ROOT / 'common' / name)
        task = 'mix-unproved'; pidfile = module / '.luoshu-state/tasks/axes_worker.pid'
        worker = self.directory / 'mix-terminal.sh'
        worker.write_text('#!/bin/sh\n' +
                          'printf "task=mix-unproved\\nstate=success\\nmessage=generated\\nstarted=1\\npercent=100\\n" > "$MODDIR/config/axes_task.conf"\n')
        injection = """import importlib.util, sys
spec=importlib.util.spec_from_file_location('scope', sys.argv[1]); scope=importlib.util.module_from_spec(spec); spec.loader.exec_module(scope)
def fail(record): raise OSError('fixture mix cleanup failed')
scope.remove_temporary=fail
sys.argv=sys.argv[1:]
sys.exit(scope.main())
"""
        # Initialize paths before the fixture worker writes its public task file.
        subprocess.run(['sh', '-c', '. "$MODDIR/common/runtime_paths.sh"; luoshu_runtime_paths_init "$MODDIR"'],
                       env=env, check=True, timeout=3)
        run = subprocess.run([sys.executable, '-c', injection, str(PROGRAM), 'run', '--pid-file', str(pidfile),
                              '--task', task, '--timeout', '5', '--', 'sh', str(worker)],
                             env=env, capture_output=True, text=True, timeout=7)
        self.assertEqual(run.returncode, 125, run.stderr)
        evidence = {suffix: Path(str(pidfile) + suffix).read_bytes() for suffix in ('', '.owner.json', '.cleanup.json')}
        router = ROOT / 'common/legacy_v14_4/mix_router.sh'
        status = subprocess.run(['sh', str(router), 'status', task], env=env, capture_output=True, text=True, timeout=5)
        self.assertEqual(json.loads(status.stdout)['data']['state'], 'cleanup-pending')
        self.assertIn('state=cleanup-pending\n', (module / 'config/axes_task.conf').read_text())
        cancel = subprocess.run(['sh', str(router), 'cancel', task], env=env, capture_output=True, text=True, timeout=5)
        self.assertEqual(cancel.returncode, 125, cancel.stderr)
        self.assertFalse(json.loads(cancel.stdout)['data']['cleaned'])
        start = subprocess.run(['sh', str(router), 'start', 'a', 'b', 'c'], env=env, capture_output=True, text=True, timeout=5)
        self.assertNotEqual(start.returncode, 0)
        self.assertEqual(json.loads(start.stdout)['status'], 'error')
        for suffix, before in evidence.items():
            self.assertEqual(Path(str(pidfile) + suffix).read_bytes(), before)
        self.assertIsNone(self.sentinel.poll())

    def test_mix_live_monitor_stays_running_then_cancel_requires_journal_recovery(self):
        module, env = self.font_module()
        for name in ('font_next_transaction.sh', 'font_switch_lock.sh'):
            (module / 'common' / name).symlink_to(ROOT / 'common' / name)
        subprocess.run(['sh', '-c', '. "$MODDIR/common/runtime_paths.sh"; luoshu_runtime_paths_init "$MODDIR"'],
                       env=env, check=True, timeout=3)
        task = 'mix-proved'; child = 'mix-child'
        taskfile = module / 'config/axes_task.conf'
        taskfile.write_text('task=' + task + '\nstate=success\nmessage=generated\nstarted=1\nchildTask=' + child + '\npercent=100\n')
        pidfile = module / '.luoshu-state/tasks/axes_worker.pid'
        proved = subprocess.run([sys.executable, str(PROGRAM), 'run', '--pid-file', str(pidfile), '--task', task,
                                 '--timeout', '5', '--', 'sh', '-c', 'exit 0'], env=env, capture_output=True, text=True, timeout=3)
        self.assertEqual(proved.returncode, 0, proved.stderr)
        monitor = module / ('.luoshu-state/tasks/mix-monitor-' + child + '.pid')
        running = subprocess.Popen([sys.executable, str(PROGRAM), 'run', '--pid-file', str(monitor), '--task', child + '.monitor',
                                    '--timeout', '15', '--', 'sh', '-c', 'sleep 30'], env=env,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(self.dispose, running)
        self.wait_for(lambda: Path(str(monitor) + '.ready').exists())
        journal = module / 'config/font-live-transaction.conf'; journal.write_text('pending\n')
        next_journal = module / '.luoshu-state/backup/next-transaction'
        next_journal.mkdir(); (next_journal / 'journal.conf').write_text('pending\n')
        router = ROOT / 'common/legacy_v14_4/mix_router.sh'
        status = subprocess.run(['sh', str(router), 'status', task], env=env, capture_output=True, text=True, timeout=5)
        self.assertEqual(json.loads(status.stdout)['data']['state'], 'running', status.stderr)
        self.assertIn('state=success\n', taskfile.read_text())
        cancel = subprocess.run(['sh', str(router), 'cancel', task], env=env, capture_output=True, text=True, timeout=7)
        self.assertEqual(cancel.returncode, 125, cancel.stderr)
        self.assertFalse(json.loads(cancel.stdout)['data']['cleaned'])
        self.assertEqual(running.wait(timeout=2), 143)
        self.assertTrue(journal.exists())
        self.assertIn('state=cleanup-pending\n', taskfile.read_text())
        (module / 'common/font_live_switch.sh').write_text('#!/bin/sh\n[ "$1" = recover ] || exit 1\n' +
                                                        'rm -f "$MODDIR/config/font-live-transaction.conf"\n' +
                                                        'rm -rf "$MODDIR/.luoshu-state/backup/next-transaction"\n')
        retry = subprocess.run(['sh', str(router), 'cancel', task], env=env, capture_output=True, text=True, timeout=7)
        self.assertEqual(retry.returncode, 0, retry.stderr)
        self.assertTrue(json.loads(retry.stdout)['data']['cleaned'])
        self.assertFalse(journal.exists())
        self.assertFalse(next_journal.exists())
        self.assertIn('state=failed\n', taskfile.read_text())
        self.assertFalse(list((module / '.luoshu-state/tasks').glob('*.pid')))
        self.assertIsNone(self.sentinel.poll())

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
