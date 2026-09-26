#!/usr/bin/env python3
"""Exercise healthy work, stuck descendants, cancellation and truthful status."""
from __future__ import annotations

import contextlib
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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'common'))
from mix_stage_watchdog import supervise, values, publish, cpu_snapshot
from mix_inventory_weights import required_weights


class WatchdogTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.module = Path(temporary.name)
        (self.module / 'config').mkdir()
        (self.module / 'config/mix-stage-next.conf').write_text('requestId=current\n')
        (self.module / 'config/axes_task.conf').write_text('task=test\n')
        self.progress = self.module / 'progress.json'

    def run_worker(self, code, idle=.4, maximum=4):
        error = io.StringIO()
        with contextlib.redirect_stderr(error):
            result = supervise(self.module, 'current', 'test', self.progress,
                               [sys.executable, '-c', code], idle, maximum, .04)
        return result, error.getvalue()

    def test_cpu_work_survives_old_wall_clock_budget_without_fake_percent(self):
        # Some managed runtimes expose the host procfs while Popen uses a PID
        # namespace. Test parsed CPU evidence separately, and feed changing ticks
        # here so the supervision decision is independent of that host mismatch.
        with patch('mix_stage_watchdog.cpu_snapshot', side_effect=lambda pid: ((pid, 1, int(time.monotonic() * 100)),)):
            result, error = self.run_worker('import time\nt=time.monotonic()\nwhile time.monotonic()-t<1.2: pass')
        self.assertEqual(result, 0, error)
        state = values(self.module / 'config/mix-finalize-state.conf')
        self.assertEqual(state['percent'], '70')
        self.assertIn('已用 1 秒', state['message'])

    def test_real_progress_survives_idle_budget_and_status_names_slot(self):
        result, error = self.run_worker('''import json,os,time
from pathlib import Path
p=Path(os.environ['LUOSHU_INVENTORY_PROGRESS_FILE'])
for count in range(1,9):
 p.write_text(json.dumps(dict(completed=count,total=9,phase='metrics',path='/system/fonts/Sans.ttf')))
 time.sleep(.16)
''')
        self.assertEqual(result, 0, error)
        state = values(self.module / 'config/mix-finalize-state.conf')
        self.assertIn('8/9', state['message'])
        self.assertIn('Sans.ttf', state['message'])
        self.assertEqual(state['percent'], '94')

    def test_idle_descendant_is_killed_not_left_writing_after_failure(self):
        marker = self.module / 'descendant.pid'
        code = f'''import subprocess,time
from pathlib import Path
child=subprocess.Popen([{sys.executable!r}, '-c', 'import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(30)'])
Path({str(marker)!r}).write_text(str(child.pid))
time.sleep(30)
'''
        result, error = self.run_worker(code)
        self.assertEqual(result, 124)
        self.assertIn('无处理进展', error)
        pid = int(marker.read_text())
        path = Path(f'/proc/{pid}/stat')
        self.assertTrue(not path.exists() or path.read_text().rsplit(') ', 1)[1].startswith('Z '))

    def test_busy_loop_still_has_absolute_limit(self):
        result, error = self.run_worker('while True: pass', idle=2, maximum=.65)
        self.assertEqual(result, 124)
        self.assertIn('总时限', error)

    def test_old_request_stops_and_cannot_overwrite_new_task(self):
        state = self.module / 'config/mix-stage-next.conf'
        task = self.module / 'config/axes_task.conf'
        result, error = self.run_worker(f'''from pathlib import Path
import time
Path({str(state)!r}).write_text('requestId=new\\n')
Path({str(task)!r}).write_text('task=new\\n')
time.sleep(30)
''')
        self.assertEqual(result, 125)
        self.assertIn('新请求', error)
        self.assertEqual(values(task)['task'], 'new')
        before = (self.module / 'config/mix-finalize-state.conf').read_bytes()
        publish(self.module, 'current', 'test', {'completed': 1, 'total': 1}, 5)
        self.assertEqual((self.module / 'config/mix-finalize-state.conf').read_bytes(), before)

    def test_signal_cancellation_stops_descendants(self):
        marker = self.module / 'mapper.pid'
        code = f'import os,time; open({str(marker)!r},"w").write(str(os.getpid())); time.sleep(30)'
        process = subprocess.Popen([sys.executable, str(ROOT / 'common/mix_stage_watchdog.py'),
            '--module', str(self.module), '--task', 'test', '--request', 'current',
            '--progress', str(self.progress), '--', sys.executable, '-c', code],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        deadline = time.monotonic() + 3
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(.02)
        self.assertTrue(marker.exists())
        process.terminate()
        _, error = process.communicate(timeout=4)
        self.assertEqual(process.returncode, 143)
        self.assertIn('已取消', error)
        self.assertFalse(Path('/proc', marker.read_text()).exists())

    def test_cpu_snapshot_counts_descendants_and_reaped_child_time(self):
        proc = self.module / 'proc'
        for pid, child, ticks in ((101, '102', [3, 4, 5, 6]), (102, '', [10, 20, 0, 0])):
            root = proc / str(pid)
            (root / 'task' / str(pid)).mkdir(parents=True)
            (root / 'task' / str(pid) / 'children').write_text(child)
            tail = ['S'] + ['0'] * 19
            tail[1] = '101' if pid == 102 else '1'
            tail[11:15] = map(str, ticks)
            tail[19] = str(pid * 10)
            (root / 'stat').write_text(f'{pid} (name with ) spaces) ' + ' '.join(tail))
        self.assertEqual(cpu_snapshot(101, proc), ((101, '1010', 18), (102, '1020', 30)))
        (proc / '101/task/101/children').unlink()
        self.assertEqual(cpu_snapshot(101, proc), ((101, '1010', 18), (102, '1020', 30)))

    def test_inventory_requests_real_weights_including_nonhundreds(self):
        data = {'slots': {'one': {'weight': 400}, 'two': {'faces': [
            {'weight': 550}, {'weight': 700}, {'weight': 400},
            {'weight': 900, 'preservedReason': 'protected-color-font'}]},
            'symbol': {'weight': 100, 'metrics': {'fontTraits': {'symbol': True}}}}}
        self.assertEqual(required_weights(data), [400, 550, 700])
        with self.assertRaises(ValueError):
            required_weights({'slots': {'broken': {'weight': 0}}})

    def test_kernel_lock_survives_killed_parent_until_child_finishes(self):
        entered, released = self.module / 'entered', self.module / 'release'
        child = f'''import os,time
from pathlib import Path
os.fstat(9)
Path({str(entered)!r}).touch()
while not Path({str(released)!r}).exists(): time.sleep(.02)
'''
        command = [sys.executable, str(ROOT / 'common/mix_stage_watchdog.py'),
                   '--module', str(self.module), '--lock', '--wait', '.2', '--']
        owner = subprocess.Popen(command + [sys.executable, '-c', child],
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 3
            while not entered.exists() and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertTrue(entered.exists())
            owner.kill()
            owner.wait(timeout=2)
            contender = subprocess.run(command + [sys.executable, '-c', 'pass'],
                                      capture_output=True, text=True, timeout=2)
            self.assertEqual(contender.returncode, 1, contender.stdout + contender.stderr)
            self.assertIn('正在提交', contender.stdout)
            released.touch()
            owner.communicate(timeout=3)
            successor = subprocess.run(command + [sys.executable, '-c', 'pass'],
                                      capture_output=True, text=True, timeout=2)
            self.assertEqual(successor.returncode, 0, successor.stdout + successor.stderr)
        finally:
            released.touch()
            if owner.poll() is None:
                owner.kill()
            owner.communicate(timeout=3)


if __name__ == '__main__':
    unittest.main(verbosity=2)
