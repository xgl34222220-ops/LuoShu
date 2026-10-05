#!/usr/bin/env python3
"""Canonical lock recovery requires the exact owned supervisor's final proof."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parents[1]


class FontSwitchLockScopeTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.module = self.directory / 'module'
        common = self.module / 'common'
        common.mkdir(parents=True)
        for name in ('font_switch_lock.sh', 'task_scope.sh', 'task_scope.py',
                     'runtime_paths.sh', 'runtime_paths_lock.py'):
            (common / name).write_bytes((ROOT / 'common' / name).read_bytes())
        (self.module / 'module.prop').write_text('id=LuoShu\n')
        self.tasks = self.module / '.luoshu-state/tasks'
        self.tasks.mkdir(parents=True)
        (self.module / '.luoshu-state/config').mkdir()
        self.lock = self.module / '.font_switch.lock'
        self.pidfile = self.tasks / 'scope.pid'
        self.env = dict(os.environ, MODULE_DIR=str(self.module), MODDIR=str(self.module),
                        LUOSHU_TASK_SCOPE_PYTHON=sys.executable,
                        LUOSHU_RUNTIME_PATHS_PYTHON=sys.executable)
        for name in tuple(self.env):
            if name.startswith(('LUOSHU_TASK_SCOPE_', 'LUOSHU_SCOPE_', 'LUOSHU_STATE_',
                                'LUOSHU_RUNTIME_PATHS_', 'LUOSHU_REAL_MODDIR', 'LUOSHU_TASKS_',
                                'LUOSHU_TMP_', 'LUOSHU_CONFIG_', 'LUOSHU_LOG_', 'LUOSHU_CACHE_',
                                'LUOSHU_BACKUP_', 'LUOSHU_REPORTS_')) and name not in (
                                    'LUOSHU_TASK_SCOPE_PYTHON', 'LUOSHU_RUNTIME_PATHS_PYTHON'):
                self.env.pop(name)

    @staticmethod
    def dispose(process):
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=7)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)

    def wait_for(self, condition, timeout=7):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if condition():
                return
            time.sleep(.02)
        self.fail('fixture did not reach the expected state')

    def shell(self, command, *, env=None):
        return subprocess.run(['sh', '-c', '. "$MODULE_DIR/common/font_switch_lock.sh"; ' + command],
                              env=env or self.env, capture_output=True, text=True, timeout=5)

    def active(self):
        return self.shell('luoshu_font_lock_active "$MODULE_DIR/.font_switch.lock"').returncode

    def acquire_and_release(self):
        return self.shell('luoshu_font_lock_acquire "$MODULE_DIR/.font_switch.lock" "$$"; '
                          'result=$?; if [ "$result" -eq 0 ]; then '
                          'luoshu_font_lock_release "$MODULE_DIR/.font_switch.lock" "$$" || exit 9; '
                          'fi; exit "$result"').returncode

    def start_scoped_worker(self, *, pidfile=None, descendant=True, expect_acquire=True):
        worker = self.directory / 'worker.sh'
        child = self.directory / 'child.py'
        child.write_text('''import json, os, signal, sys, time
from pathlib import Path
signal.signal(signal.SIGTERM, signal.SIG_IGN)
Path(sys.argv[1]).write_text(json.dumps({'pid': os.getpid(), 'procPid': int(os.readlink('/proc/self'))}))
while True: time.sleep(.02)
''')
        worker.write_text('''. "$MODULE_DIR/common/font_switch_lock.sh"
luoshu_font_lock_acquire "$MODULE_DIR/.font_switch.lock" "$$" || exit 8
printf '%s\\n' "$$" > "$MODULE_DIR/worker.pid"
if [ "$1" = descendant ]; then
    "$LUOSHU_TASK_SCOPE_PYTHON" "$2" "$MODULE_DIR/child.json" &
fi
while :; do sleep .02; done
''')
        process = subprocess.Popen(['sh', str(self.module / 'common/task_scope.sh'), 'run',
                                    '--pid-file', str(pidfile or self.pidfile), '--task', 'lock-owned-task',
                                    '--timeout', '20', '--', 'sh', str(worker),
                                    'descendant' if descendant else 'none', str(child)],
                                   env=self.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(self.dispose, process)
        if not expect_acquire:
            process.wait(timeout=7)
            return process
        self.wait_for(lambda: (self.module / 'worker.pid').exists() and
                      (not descendant or (self.module / 'child.json').exists()))
        return process

    def test_killed_shell_waits_for_exact_cleanup_then_reacquires_without_lease(self):
        supervisor = self.start_scoped_worker()
        record_path = self.lock / 'pid'
        original_record = record_path.read_text()
        values = dict(line.split('=', 1) for line in original_record.splitlines()[1:])
        owner = json.loads(Path(str(self.pidfile) + '.owner.json').read_text())
        self.assertEqual(values['scope_pidfile'], str(self.pidfile))
        for saved, key in (('scope_task', 'task'), ('scope_pid', 'pid'),
                           ('scope_start', 'start'), ('scope_boot', 'boot'), ('scope_namespace', 'namespace')):
            self.assertEqual(values[saved], str(owner[key]))
        self.assertEqual(supervisor.pid, owner['pid'])
        shell_pid = int((self.module / 'worker.pid').read_text())
        # This PID was created by this fixture's supervisor; no process-name or
        # process-group lookup/kill is involved.
        os.kill(shell_pid, signal.SIGKILL)
        self.assertIsNone(supervisor.poll())
        self.assertEqual(self.active(), 0, 'dead shell retired before descendants were cleaned')
        self.assertEqual(self.acquire_and_release(), 2)
        supervisor.wait(timeout=7)
        self.assertEqual(supervisor.returncode, 137)
        proof_path = Path(str(self.pidfile) + '.cleanup.json')
        proof_text = proof_path.read_text()
        proof = json.loads(proof_text)
        self.assertTrue(proof['cleaned'])
        self.assertEqual(proof['leftoverPids'], [])
        self.assertEqual(proof['cleanupErrors'], [])
        self.assertEqual(proof['handoffTasks'], [])
        self.assertEqual(proof['handoffOwners'], [])
        self.assertFalse(Path(str(self.pidfile) + '.owner.json').exists())
        self.assertEqual(record_path.read_text(), original_record)

        changes = {'task': 'another-task', 'pid': proof['pid'] + 1,
                   'start': str(int(proof['start']) + 1), 'boot': 'another-boot',
                   'namespace': 'pid:[another-namespace]',
                   'cleaned': False, 'leftoverPids': [proof['pid']],
                   'cleanupErrors': ['unknown'], 'handoffTasks': ['nested-task'],
                   'handoffOwners': [{'task': 'nested-task'}]}
        for key, wrong in changes.items():
            with self.subTest(wrong_proof_field=key):
                proof_path.write_text(json.dumps(dict(proof, **{key: wrong})))
                self.assertEqual(self.active(), 0)
                self.assertEqual(self.acquire_and_release(), 2)
                self.assertEqual(record_path.read_text(), original_record)

        # Unknown scoped children do not become safe just because their old
        # namespace lease has expired.
        proof_path.write_text(json.dumps(dict(proof, cleaned=False)))
        record_path.write_text(original_record.replace('created=' + values['created'], 'created=0'))
        self.assertEqual(self.active(), 0)
        self.assertEqual(self.acquire_and_release(), 2)
        record_path.write_text(original_record)
        proof_path.write_text(proof_text)

        # A replacement registration blocks reuse of the old slot's proof.
        replacement = Path(str(self.pidfile) + '.owner.json')
        replacement.write_text(json.dumps(owner))
        self.assertEqual(self.active(), 0)
        self.assertEqual(self.acquire_and_release(), 2)
        replacement.unlink()

        # A proof outside the centralized module tree cannot authorize release,
        # even if all its identity fields are copied from a genuine proof.
        outside = self.directory / 'outside.pid'
        Path(str(outside) + '.cleanup.json').write_text(proof_text)
        record_path.write_text(original_record.replace('scope_pidfile=' + str(self.pidfile),
                                                       'scope_pidfile=' + str(outside)))
        self.assertEqual(self.active(), 0)
        self.assertEqual(self.acquire_and_release(), 2)
        record_path.write_text(original_record)

        self.assertEqual(self.active(), 1)
        started = time.monotonic()
        self.assertEqual(self.acquire_and_release(), 0)
        self.assertLess(time.monotonic() - started, 2, 'reacquisition waited for the 480 s lease')
        self.assertFalse(self.lock.exists())

        # Even the exact cleaned task proof cannot retire a currently live
        # canonical owner. Use only an independently created fixture process.
        sentinel_output = self.directory / 'sentinel.json'
        sentinel = subprocess.Popen([sys.executable, '-c',
            'import json,os,sys,time; from pathlib import Path; '
            'p=int(os.readlink("/proc/self")); '
            's=Path("/proc/"+str(p)+"/stat").read_text().rsplit(") ",1)[1].split()[19]; '
            'Path(sys.argv[1]).write_text(json.dumps({"pid":p,"start":s})); time.sleep(30)',
            str(sentinel_output)], env=self.env)
        self.addCleanup(self.dispose, sentinel)
        self.wait_for(sentinel_output.exists)
        sentinel_identity = json.loads(sentinel_output.read_text())
        lines = original_record.splitlines()
        lines[0] = str(sentinel_identity['pid'])
        lines = ['starttime=' + sentinel_identity['start'] if line.startswith('starttime=') else line
                 for line in lines]
        self.lock.mkdir()
        record_path.write_text('\n'.join(lines) + '\n')
        self.assertEqual(self.active(), 0)
        self.assertEqual(self.acquire_and_release(), 2)
        self.assertIsNone(sentinel.poll())

    def test_scope_pointer_outside_module_state_is_refused(self):
        supervisor = self.start_scoped_worker(pidfile=self.directory / 'outside.pid',
                                             descendant=False, expect_acquire=False)
        self.assertEqual(supervisor.returncode, 8)
        self.assertFalse(self.lock.exists())

    def test_borrowed_live_scope_environment_is_refused(self):
        supervisor = self.start_scoped_worker(descendant=False)
        owner = json.loads(Path(str(self.pidfile) + '.owner.json').read_text())
        borrowed = dict(self.env, LUOSHU_TASK_SCOPE_PIDFILE=str(self.pidfile),
                        LUOSHU_TASK_SCOPE_PID=str(owner['pid']), LUOSHU_TASK_SCOPE_TASK=owner['task'])
        result = self.shell('path="$MODULE_DIR/.borrowed.lock"; '
                            'luoshu_font_lock_acquire "$path" "$$" || exit 8; '
                            'cat "$path/pid"; luoshu_font_lock_release "$path" "$$"', env=borrowed)
        self.assertEqual(result.returncode, 8, result.stderr)
        self.assertFalse((self.module / '.borrowed.lock').exists())
        self.dispose(supervisor)

    def test_partial_scope_environment_is_refused(self):
        env = dict(self.env, LUOSHU_TASK_SCOPE_PIDFILE=str(self.pidfile))
        result = self.shell('luoshu_font_lock_acquire "$MODULE_DIR/.font_switch.lock" "$$"', env=env)
        self.assertEqual(result.returncode, 1)
        self.assertFalse(self.lock.exists())

    def test_reaper_does_not_delete_a_replacement_record(self):
        self.lock.mkdir()
        (self.lock / 'pid').write_text('99999999\nstarttime=1\nboot_id=old-boot\ntoken=old\n')
        replacement = '99999998\nstarttime=2\nboot_id=new-boot\ntoken=new\n'
        (self.module / 'replacement').write_text(replacement)
        result = self.shell('luoshu_font_lock_active() { '
                            'cp "$MODULE_DIR/replacement" "$1/pid"; return 1; }; '
                            'luoshu_font_lock_reap_stale "$MODULE_DIR/.font_switch.lock"')
        self.assertEqual(result.returncode, 1)
        self.assertEqual((self.lock / 'pid').read_text(), replacement)

    def finished_lock(self):
        boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        namespace = os.readlink('/proc/self/ns/pid')
        proof = dict(schema='task-cleanup-v2', task='finished-task', pid=99999997,
                     start='123', boot=boot, namespace=namespace, cleaned=True,
                     leftoverPids=[], cleanupErrors=[], handoffTasks=[], handoffOwners=[])
        Path(str(self.pidfile) + '.cleanup.json').write_text(json.dumps(proof))
        self.lock.mkdir()
        record = ('99999999\nstarttime=123\nboot_id=' + boot + '\ntoken=finished-token\ncreated=' +
                  str(int(time.time())) + '\nscope_pidfile=' + str(self.pidfile) +
                  '\nscope_task=finished-task\nscope_pid=99999997\nscope_start=123\nscope_boot=' +
                  boot + '\nscope_namespace=' + namespace + '\n')
        (self.lock / 'pid').write_text(record)
        return record

    def start_paused_reaper(self, phase):
        instrumentation = self.directory / 'instrumentation'
        instrumentation.mkdir()
        # Fault injection affects only this fixture's Python process. Pause at
        # the actual deletion or flock syscall, after the shell's final reread.
        (instrumentation / 'sitecustomize.py').write_text('''import fcntl, os, time
from pathlib import Path
def pause():
    Path(os.environ['LOCK_TEST_GATE']).write_text('ready')
    while not Path(os.environ['LOCK_TEST_RESUME']).exists(): time.sleep(.01)
if os.environ['LOCK_TEST_PHASE'] == 'before-flock':
    original = fcntl.flock
    def flock(*args, **kwargs):
        pause()
        return original(*args, **kwargs)
    fcntl.flock = flock
else:
    original = Path.unlink
    def unlink(self, *args, **kwargs):
        if self.name == 'pid' and self.parent.name == '.font_switch.lock': pause()
        return original(self, *args, **kwargs)
    Path.unlink = unlink
''')
        gate = self.directory / 'reap-gate'
        resume = self.directory / 'reap-resume'
        env = dict(self.env, PYTHONPATH=str(instrumentation), LOCK_TEST_PHASE=phase,
                   LOCK_TEST_GATE=str(gate), LOCK_TEST_RESUME=str(resume))
        process = subprocess.Popen(['sh', '-c', '. "$MODULE_DIR/common/font_switch_lock.sh"; '
                                    'luoshu_font_lock_reap_stale "$MODULE_DIR/.font_switch.lock"'],
                                   env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(self.dispose, process)
        self.wait_for(gate.exists)
        return process, resume

    def test_concurrent_reaper_cannot_delete_new_live_winner_after_its_reread(self):
        old_record = self.finished_lock()
        reaper, resume = self.start_paused_reaper('before-flock')
        winner = subprocess.Popen(['sh', '-c', '. "$MODULE_DIR/common/font_switch_lock.sh"; '
                                   'luoshu_font_lock_acquire "$MODULE_DIR/.font_switch.lock" "$$" || exit 8; '
                                   'printf "ready\\n"; read command; '
                                   'luoshu_font_lock_release "$MODULE_DIR/.font_switch.lock" "$$"'],
                                  env=self.env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, text=True)
        self.addCleanup(self.dispose, winner)
        self.assertEqual(winner.stdout.readline(), 'ready\n')
        new_record = (self.lock / 'pid').read_text()
        self.assertNotEqual(old_record, new_record)
        resume.touch()
        self.assertEqual(reaper.wait(timeout=5), 1)
        self.assertEqual((self.lock / 'pid').read_text(), new_record)
        self.assertEqual(self.active(), 0)
        self.assertEqual(self.acquire_and_release(), 2)
        self.assertIsNone(winner.poll())
        winner.communicate('release\n', timeout=5)
        self.assertEqual(winner.returncode, 0)

    def test_reapers_serialize_the_check_and_delete_and_release_kernel_lock(self):
        old_record = self.finished_lock()
        reaper, resume = self.start_paused_reaper('before-unlink')
        self.assertEqual(self.acquire_and_release(), 2)
        self.assertEqual((self.lock / 'pid').read_text(), old_record)
        resume.touch()
        self.assertEqual(reaper.wait(timeout=5), 0)
        self.assertFalse(self.lock.exists())
        self.assertEqual(self.acquire_and_release(), 0)

    def test_unassociated_namespace_lease_remains_unchanged(self):
        self.lock.mkdir()
        boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        created = str(int(time.time()))
        (self.lock / 'pid').write_text('99999999\nstarttime=123\nboot_id=' + boot +
                                      '\ntoken=legacy\ncreated=' + created + '\n')
        self.assertEqual(self.active(), 0)
        self.assertEqual(self.acquire_and_release(), 2)
        (self.lock / 'pid').write_text((self.lock / 'pid').read_text().replace(
                                      'created=' + created, 'created=0'))
        self.assertEqual(self.active(), 1)
        self.assertEqual(self.acquire_and_release(), 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
