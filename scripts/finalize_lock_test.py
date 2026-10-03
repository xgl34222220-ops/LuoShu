#!/usr/bin/env python3
"""Kernel-lock ownership tests for the real legacy finalizer shell functions."""
import fcntl
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FinalizeLockTest(unittest.TestCase):
    shell = 'sh'

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='luoshu-finalize-lock-')
        self.addCleanup(self.temp.cleanup)
        self.module = Path(self.temp.name) / 'module'
        (self.module / 'common').mkdir(parents=True)
        (self.module / 'config').mkdir()
        for name in ('background_task.sh', 'task_scope.py'):
            shutil.copyfile(ROOT / 'common' / name, self.module / 'common' / name)
        text = (ROOT / 'common/legacy_v14_4/mix_router.sh').read_text()
        functions = '\n'.join(re.search(r'^' + name + r'\(\) \{\n.*?^\}', text,
                                         re.M | re.S).group(0)
                              for name in ('finalize_lock_acquire', 'finalize_lock_release'))
        self.functions = Path(self.temp.name) / 'functions.sh'
        self.functions.write_text(functions)
        self.env = dict(os.environ, REALMOD=str(self.module), MODDIR=str(self.module),
                        FINALIZE_LOCK=str(self.module / '.mix-stage-finalize.lock'),
                        LUOSHU_TASK_HELPER=str(self.module / 'common/task_scope.py'))
        self.lockfile = self.module / 'config/mix-finalize.flock'

    def script(self, body):
        return [self.shell, '-c', '. "$1"; ' + body, 'sh', str(self.functions)]

    def call(self, body='finalize_lock_acquire || exit 4; finalize_lock_release'):
        return subprocess.run(self.script(body), env=self.env, capture_output=True,
                              text=True, timeout=5)

    def holder(self):
        process = subprocess.Popen(self.script(
            'finalize_lock_acquire || exit 4; echo ready; read -r released; finalize_lock_release'),
            env=self.env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        def cleanup():
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=3)
        self.addCleanup(cleanup)
        # Bounded readiness without blocking on a failed shell fixture.
        import select
        self.assertTrue(select.select([process.stdout], [], [], 5)[0])
        self.assertEqual(process.stdout.readline().strip(), 'ready')
        return process

    def test_helper_exit_does_not_release_callers_lock(self):
        holder = self.holder()
        with self.lockfile.open('a') as competitor:
            with self.assertRaises(BlockingIOError):
                fcntl.flock(competitor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        self.assertIsNone(holder.poll())

    def test_sigkill_owner_unblocks_waiter_without_pid_cleanup(self):
        holder = self.holder()
        waiter = subprocess.Popen(self.script(
            'finalize_lock_acquire || exit 4; echo acquired; finalize_lock_release'),
            env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        time.sleep(.15)
        self.assertIsNone(waiter.poll(), 'waiter entered while owner was alive')
        holder.kill()
        holder.wait(timeout=3)
        out, err = waiter.communicate(timeout=5)
        self.assertEqual(waiter.returncode, 0, err)
        self.assertEqual(out.strip(), 'acquired')

    def test_failed_owner_releases_kernel_lock_on_exit(self):
        failed = self.call('finalize_lock_acquire || exit 4; exit 7')
        self.assertEqual(failed.returncode, 7, failed.stderr)
        recovered = self.call()
        self.assertEqual(recovered.returncode, 0, recovered.stderr)

    def test_recycled_legacy_pid_has_no_lock_or_signal_authority(self):
        sentinel = subprocess.Popen(['/bin/sleep', '30'])
        self.addCleanup(lambda: (sentinel.kill() if sentinel.poll() is None else None,
                                 sentinel.wait(timeout=3)))
        old = self.module / '.mix-stage-finalize.lock'
        old.mkdir()
        (old / 'pid').write_text(str(sentinel.pid) + '\n')
        result = self.call()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIsNone(sentinel.poll(), 'a reused PID was signalled')

    def test_release_preserves_inode_for_already_open_waiters(self):
        self.assertEqual(self.call().returncode, 0)
        inode = self.lockfile.stat().st_ino
        self.assertEqual(self.call().returncode, 0)
        self.assertEqual(self.lockfile.stat().st_ino, inode)

    def test_contention_timeout_does_not_remove_active_lock(self):
        holder = self.holder()
        result = self.call(
            '. "$REALMOD/common/background_task.sh"; '
            'exec 9>>"$REALMOD/config/mix-finalize.flock"; '
            'luoshu_task_helper lock-fd 9 0.1; rc=$?; exec 9>&-; exit "$rc"')
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('lock-fd timeout fd=9 errno=11 (EAGAIN)', result.stderr)
        self.assertTrue(self.lockfile.exists())
        self.assertIsNone(holder.poll())


    def test_closed_descriptor_reports_ebadf_without_waiting(self):
        result = subprocess.run(['python3', str(self.module / 'common/task_scope.py'),
                                 'lock-fd', '9', '20'], env=self.env,
                                capture_output=True, text=True, timeout=2)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('lock-fd failed fd=9 errno=9 (EBADF)', result.stderr)

    def test_other_helper_actions_do_not_require_descriptor_nine(self):
        (self.module / 'output.log').write_text('{"message":"helper without fd9"}\n')
        result = self.call(
            '. "$REALMOD/common/background_task.sh"; exec 9>&-; '
            'luoshu_task_helper error-message "$REALMOD/output.log"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'helper without fd9')


MKSH = os.environ.get('LUOSHU_TEST_MKSH') or shutil.which('mksh')


@unittest.skipUnless(MKSH, 'mksh is required in candidate CI; optional on a minimal host')
class MkshFinalizeLockTest(FinalizeLockTest):
    """Android mksh makes exec-created fds private unless explicitly exported."""
    shell = MKSH

    def test_original_unexported_exec_boundary_is_ebadf(self):
        # Control reproduces the pre-fix shell boundary without requiring a
        # competing owner or depending on this test suite's implementation.
        result = subprocess.run([self.shell, '-c',
            'exec 9>>"$REALMOD/config/control.flock"; '
            'python3 -c "import os; os.fstat(9)"'], env=self.env,
            capture_output=True, text=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('[Errno 9] Bad file descriptor', result.stderr)


if __name__ == '__main__':
    unittest.main()
