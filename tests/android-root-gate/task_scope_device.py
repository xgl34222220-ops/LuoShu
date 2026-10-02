#!/usr/bin/env python3
"""Run with the shipped Python on a disposable rooted Android emulator.

Does not import unittest (intentionally absent from the shipped runtime).
Only synthetic processes and a per-run temporary module directory are used.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def wait_for(check, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(.05)
    raise RuntimeError('Condition did not converge within cleanup deadline')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--helper', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    report = {'result': 'FAIL', 'scope': 'candidate task helper only; not module delivery', 'cases': []}
    try:
        require(Path('/system/bin/getprop').exists(), 'Android runtime required')
        require(subprocess.check_output(['/system/bin/getprop', 'ro.kernel.qemu']).strip() == b'1', 'Disposable AVD required')
        require(os.getuid() == 0, 'Root required')
        spec = importlib.util.spec_from_file_location('scope_under_test', args.helper)
        scope = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(scope)
        report['pidfd_backend'] = {'open_supported': False, 'send_zero_supported': False}
        try:
            fd = scope.pidfd_open(os.getpid())
            report['pidfd_backend']['open_supported'] = True
            try:
                scope.pidfd_send(fd, 0)
                report['pidfd_backend']['send_zero_supported'] = True
            finally:
                os.close(fd)
        except OSError as error:
            report['pidfd_backend']['errno'] = error.errno
        report['boot_id'] = scope.boot_id()
        report['selinux'] = subprocess.check_output(['/system/bin/getenforce'], text=True).strip()
        with tempfile.TemporaryDirectory(prefix='luoshu-task-gate-', dir='/data/local/tmp') as temp:
            root = Path(temp)
            for mode in ('success', 'failure', 'timeout', 'cancel'):
                module = root / mode
                config = module / 'config'
                config.mkdir(parents=True)
                leaf_file = module / 'leaf.json'
                pidfile = config / 'switch_task_worker.pid'
                task = 'android-gate-' + mode
                env = dict(os.environ, MODDIR=str(module), TMPDIR=str(module),
                           LUOSHU_TASK_TIMEOUT_SECONDS='1' if mode == 'timeout' else '30')
                (config / 'switch_task.conf').write_text('task=' + task + '\nstate=running\n')
                code = f'''
import json, os, signal, time
from pathlib import Path
if os.fork() == 0:
    os.setsid()
    if os.fork() != 0: os._exit(0)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    tail=Path('/proc/self/stat').read_text().rsplit(') ',1)[1].split()
    Path({str(leaf_file)!r}).write_text(json.dumps({{'pid':os.getpid(),'start':int(tail[19])}}))
    while True: time.sleep(.05)
while not Path({str(leaf_file)!r}).exists(): time.sleep(.01)
Path(os.environ['LUOSHU_TASK_WORK_DIR'], 'synthetic.tmp').write_text('synthetic')
{'time.sleep(60)' if mode in ('timeout','cancel') else 'time.sleep(.1)'}
os._exit({7 if mode == 'failure' else 0})
'''
                sentinel = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(90)', task], env=env)
                sentinel_identity = scope.proc_info(sentinel.pid)
                case = {'mode': mode, 'result': 'FAIL', 'sentinel': sentinel_identity}
                report['cases'].append(case)
                try:
                    subprocess.run([sys.executable, str(args.helper), 'launch', str(pidfile), task,
                                    str(module / 'task.log'), '--', sys.executable, '-c', code],
                                   env=env, check=True, timeout=15)
                    leaf = json.loads(wait_for(lambda: scope.read(leaf_file)))
                    case['owned_leaf'] = leaf
                    case['supervisor_identity'] = scope.read(str(pidfile) + '.identity')
                    if mode == 'cancel':
                        subprocess.run([sys.executable, str(args.helper), 'stop', str(pidfile), task],
                                       env=env, check=True, timeout=15)
                    wait_for(lambda: not Path(str(pidfile) + '.identity').exists())
                    require(not Path('/proc', str(leaf['pid'])).exists(), 'Owned child or zombie remains')
                    require(not list((module / 'cache/tasks').glob('*/.luoshu-task-owner')), 'Owned work directory remains')
                    require(scope.same_process(sentinel_identity), 'Independent sentinel killed or replaced')
                    # Check again after completion to catch delayed/orphaned work.
                    time.sleep(1)
                    require(not Path('/proc', str(leaf['pid'])).exists(), 'Owned process appeared after completion')
                    require(scope.same_process(sentinel_identity), 'Sentinel did not survive delayed check')
                    if mode == 'timeout':
                        require('执行超时' in scope.read(config / 'switch_task.conf'), 'Timeout state not published')
                    case['result'] = 'PASS'
                finally:
                    subprocess.run([sys.executable, str(args.helper), 'stop', str(pidfile), task],
                                   env=env, timeout=15, check=False)
                    if sentinel.poll() is None:
                        sentinel.terminate()
                    try:
                        sentinel.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        sentinel.kill(); sentinel.wait(timeout=5)
        report['result'] = 'PASS'
    except Exception as error:
        report['error'] = str(error)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    return 0 if report['result'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
