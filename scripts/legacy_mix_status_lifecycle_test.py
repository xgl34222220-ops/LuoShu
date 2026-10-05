#!/usr/bin/env python3
"""App polling reconciles dead detached mix workers without rebuilding fonts."""
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


class MixStatusLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.module = Path(self.temp.name) / 'module'
        self.config = self.module / 'config'
        self.config.mkdir(parents=True)
        (self.module / 'common').mkdir()
        for name in ('background_task.sh','task_scope.sh','task_scope.py','runtime_paths.sh','runtime_paths_lock.py'):
            (self.module / 'common' / name).symlink_to(ROOT / 'common' / name)
        self.task_file = self.config / 'axes_task.conf'
        self.boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        self.env = {**os.environ, 'MODDIR': str(self.module), 'LUOSHU_TASK_SCOPE_PYTHON': sys.executable,
                    'LUOSHU_RUNTIME_PATHS_PYTHON': sys.executable}
        subprocess.run(['sh','-c','. "$1"; luoshu_runtime_paths_init "$2"','sh',
                        str(self.module / 'common/runtime_paths.sh'),str(self.module)],env=self.env,check=True,timeout=5)
        self.tasks = self.module / '.luoshu-state/tasks'
        self.write_task()

    def write_task(self, task='axes-stale', state='running', started=None):
        if started is None:
            started = int(time.time()) - 120
        self.task_file.write_text(
            f'task={task}\nstate={state}\nstarted={started}\nmessage=working\n'
            'percent=34\ncjk=测试字体\nlatin=Latin\ndigit=Digits\n'
            'cjkAxes=wght=440\nroot=/preserve-this-cache\nchildTask=mix-child\n')

    def call(self, command='status'):
        result = subprocess.run(['sh', str(ROOT / 'common/legacy_v14_4/mix_router.sh'), command],
                                env=self.env, text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.module / '.luoshu-state/cache/legacy-v14-runtime').exists())
        self.assertFalse((self.module / '.luoshu-state/tmp/mix-stage').exists())
        self.assertFalse((self.module / '.luoshu-payload').exists())
        self.assertFalse(list(self.config.glob('*.reconcile.*')))
        return json.loads(result.stdout)

    def worker(self, task='axes-stale', sidecar_task=None, boot=None, name='axes_worker.pid'):
        # Keep an actual process with the task as one exact argv entry. No fake
        # kill/stat functions: test the same /proc and PID checks used on device.
        path = self.tasks / name
        process = subprocess.Popen(['sh',str(self.module / 'common/task_scope.sh'),'run','--pid-file',str(path),
                                    '--task',task,'--timeout','60','--','sh','-c','read line','mix-test-worker',task],
                                   stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=self.env)
        def stop():
            if process.poll() is None:
                process.terminate()
            process.communicate(timeout=6)
        self.addCleanup(stop)
        end = time.monotonic() + 5
        while not Path(str(path)+'.ready').exists() and time.monotonic() < end: time.sleep(.01)
        self.assertTrue(Path(str(path)+'.ready').exists())
        Path(str(path) + '.task').write_text((sidecar_task or task) + '\n')
        Path(str(path) + '.boot').write_text((boot or self.boot) + '\n')
        return process, path

    def test_dead_worker_is_failed_and_metadata_is_preserved(self):
        path = self.tasks / 'axes_worker.pid'
        path.write_text('99999999\n')
        Path(str(path) + '.task').write_text('axes-stale\n')
        data = self.call()['data']
        self.assertEqual((data['state'], data['progress']['percent']), ('failed', 100))
        self.assertEqual(data['cjk'], '测试字体')
        saved = self.task_file.read_text()
        self.assertIn('root=/preserve-this-cache\n', saved)
        self.assertIn('childTask=mix-child\n', saved)
        self.assertFalse(path.exists())

    def test_home_reconcile_also_releases_dead_task(self):
        self.assertEqual(self.call('reconcile'), {'status': 'ok'})
        self.assertIn('state=failed\n', self.task_file.read_text())

    def test_current_axes_and_auto_workers_remain_running(self):
        for name in ('axes_worker.pid', 'auto_multiweight_worker.pid'):
            with self.subTest(name=name):
                process, path = self.worker(name=name)
                self.assertEqual(self.call()['data']['state'], 'running')
                process.terminate()
                process.communicate(timeout=6)
                for suffix in ('', '.task', '.boot'):
                    Path(str(path) + suffix).unlink(missing_ok=True)

    def test_started_worker_without_sidecars_has_grace(self):
        for state in ('queued', 'running'):
            with self.subTest(state=state):
                self.write_task(state=state, started=int(time.time()))
                self.assertEqual(self.call()['data']['state'], state)

    def test_previous_boot_pid_is_rejected_without_killing_process(self):
        process, _ = self.worker(boot='previous-boot')
        self.assertEqual(self.call()['data']['state'], 'failed')
        self.assertIsNone(process.poll())

    def test_reused_pid_with_other_task_preserves_its_sidecars(self):
        process, path = self.worker(task='axes-new')
        self.assertEqual(self.call()['data']['state'], 'failed')
        self.assertIsNone(process.poll())
        self.assertEqual(Path(str(path) + '.task').read_text(), 'axes-new\n')

    def test_task_prefix_is_not_the_same_worker(self):
        process, _ = self.worker(task='axes-stale-new', sidecar_task='axes-stale')
        self.assertEqual(self.call()['data']['state'], 'failed')
        self.assertIsNone(process.poll())

    def test_new_request_during_reconcile_is_not_overwritten(self):
        directory = Path(self.temp.name) / 'bin'
        directory.mkdir()
        date = directory / 'date'
        date.write_text('#!/bin/sh\nprintf "task=axes-new\\nstate=queued\\nstarted=9999999999\\n" '
                        '> "$MODDIR/config/axes_task.conf"\nexec /bin/date "$@"\n')
        date.chmod(0o755)
        self.env['PATH'] = f'{directory}:{self.env["PATH"]}'
        self.call('reconcile')
        self.assertIn('task=axes-new\nstate=queued\n', self.task_file.read_text())


if __name__ == '__main__':
    unittest.main()
