#!/usr/bin/env python3
"""Actual Android mksh/ARM64 fd transport; isolated synthetic lock files only."""
import argparse
import errno
import fcntl
import json
import os
from pathlib import Path
import select
import shlex
import subprocess
import sys
import tempfile
import time


def fd_observation(fd=9):
    result = {}
    for label, operation in (('fstat', lambda: os.fstat(fd)),
                             ('flock', lambda: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB))):
        try:
            operation()
            result[label + '_errno'] = 0
        except OSError as error:
            result[label + '_errno'] = error.errno
            result[label + '_error'] = errno.errorcode.get(error.errno, str(error))
    return result


def execute(module, report):
    if (not Path('/system/bin/sh').is_file() or os.getuid() != 0 or
            subprocess.check_output(['getprop', 'ro.kernel.qemu'], text=True).strip() != '1' or
            subprocess.check_output(['getenforce'], text=True).strip() != 'Enforcing'):
        raise RuntimeError('Only the authorized root Enforcing Android emulator is supported')
    report['environment'] = 'ACTUAL_ANDROID_QEMU_ROOT_ENFORCING'
    report['shell'] = os.path.realpath('/system/bin/sh')
    report['runtime'] = sys.executable
    processes = []
    with tempfile.TemporaryDirectory(prefix='luoshu-lock-gate-', dir='/data/local/tmp') as tmp:
        lock = Path(tmp) / 'probe.flock'
        env = dict(os.environ, MODDIR=str(module), LUOSHU_REAL_MODDIR=str(module))
        control = 'exec 9>>' + shlex.quote(str(lock)) + '; ' + shlex.join([
            sys.executable, str(Path(__file__).resolve()), '--inspect-fd'])
        old = subprocess.run(['/system/bin/sh', '-c', control], env=env,
                             capture_output=True, text=True, timeout=20)
        report['unexported_fd_control'] = dict(json.loads(old.stdout.strip().splitlines()[-1]),
                                             exit=old.returncode, stderr=old.stderr)
        if (old.returncode or report['unexported_fd_control'].get('fstat_errno') != errno.EBADF or
                report['unexported_fd_control'].get('flock_errno') != errno.EBADF):
            raise RuntimeError('Android unexported descriptor control did not reproduce EBADF')
        prefix = '. ' + shlex.quote(str(module / 'common/background_task.sh')) + '; exec 9>>' + shlex.quote(str(lock)) + '; '
        def launch(body):
            process = subprocess.Popen(['/system/bin/sh', '-c', prefix + body], env=env,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            processes.append(process)
            return process
        try:
            holder = launch('luoshu_task_helper lock-fd 9 3 || exit 4; echo READY; read -r released; exec 9>&-')
            if not select.select([holder.stdout], [], [], 20)[0] or holder.stdout.readline().strip() != 'READY':
                raise RuntimeError('Installed helper did not transfer fd 9 to Python')
            inode = lock.stat().st_ino
            with lock.open('a') as competitor:
                try:
                    fcntl.flock(competitor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as error:
                    report['caller_retains_lock'] = {'result': 'PASS', 'errno': error.errno}
                else:
                    raise RuntimeError('Helper exit released caller lock prematurely')
            timeout = subprocess.run(['/system/bin/sh', '-c', prefix +
                'luoshu_task_helper lock-fd 9 0.2'], env=env, capture_output=True, text=True, timeout=20)
            report['contention'] = {'exit': timeout.returncode, 'stdout': timeout.stdout, 'stderr': timeout.stderr}
            if timeout.returncode != 1 or 'errno=11 (EAGAIN)' not in timeout.stderr:
                raise RuntimeError('Real lock contention was not distinguished from EBADF')
            waiter = launch('luoshu_task_helper lock-fd 9 3 || exit 4; echo ACQUIRED; exec 9>&-')
            # An independent fcntl contender above proves exclusion without
            # using timing alone; the queued real shell must then acquire too.
            time.sleep(.2)
            report['waiter_blocked_while_owned'] = waiter.poll() is None
            if not report['waiter_blocked_while_owned']:
                raise RuntimeError('Second real shell entered while first caller owned lock')
            holder_out, holder_err = holder.communicate('release\n', timeout=20)
            waiter_out, waiter_err = waiter.communicate(timeout=20)
            report['owner_release'] = {'exit': holder.returncode, 'stdout': holder_out, 'stderr': holder_err}
            report['waiter_after_release'] = {'exit': waiter.returncode, 'stdout': waiter_out, 'stderr': waiter_err}
            if holder.returncode != 0 or waiter.returncode != 0 or waiter_out.strip() != 'ACQUIRED':
                raise RuntimeError('Queued real shell did not acquire after caller release')
            report['persistent_inode_preserved'] = lock.stat().st_ino == inode
            if not report['persistent_inode_preserved']:
                raise RuntimeError('Lock file inode was replaced')
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                process.communicate(timeout=25)
    report['result'] = 'PASS'


def main():
    if sys.argv[1:] == ['--inspect-fd']:
        print(json.dumps(fd_observation()))
        return 0
    parser = argparse.ArgumentParser()
    parser.add_argument('--module', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    report = {'result': 'FAIL'}
    try:
        execute(args.module, report)
    except Exception as error:
        report['error'] = str(error)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    return 0 if report['result'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
