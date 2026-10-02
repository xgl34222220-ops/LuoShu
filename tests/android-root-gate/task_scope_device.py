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


def read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


def identity(scope, record, boot, token=None):
    require(isinstance(record, dict) and record.get('pid') and record.get('start'),
            'Missing exact process identity')
    result = dict(record, boot=boot)
    if token is not None:
        result['token'] = token
    require(boot and scope.boot_id() == boot, 'Process identity belongs to another boot')
    return result


def same_identity(scope, record):
    return scope.boot_id() == record['boot'] and scope.same_process(record, include_zombie=True)


def fixture_code(module, task, mode):
    # All records are atomically published before the parent releases the worker.
    # The escaping leaf makes a second detached child only AFTER receiving TERM.
    return f'''
import json, os, signal, time
from pathlib import Path
root = Path({str(module)!r})
task = {task!r}
mode = {mode!r}
def publish(name, data):
    target = root / name
    temporary = target.with_name(target.name + '.tmp.' + str(os.getpid()))
    temporary.write_text(json.dumps(data))
    os.replace(temporary, target)
def record(name):
    tail = Path('/proc/self/stat').read_text().rsplit(') ', 1)[1].split()
    publish(name, {{'pid': os.getpid(), 'ppid': int(tail[1]), 'start': int(tail[19]),
                   'boot': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                   'token': os.environ['LUOSHU_TASK_SCOPE']}})
record('worker.json')
if os.fork() == 0:
    os.setsid()
    if os.fork() != 0:
        record('intermediate.json')
        os._exit(0)
    spawned = False
    def term(_number, _frame):
        global spawned
        if spawned:
            return
        spawned = True
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        if os.fork() == 0:
            os.setsid()
            record('late-leaf.json')
            while True:
                time.sleep(.05)
    signal.signal(signal.SIGTERM, term)
    record('leaf.json')
    while True:
        time.sleep(.05)
while not (root / 'leaf.json').exists():
    time.sleep(.01)
Path(os.environ['LUOSHU_TASK_WORK_DIR'], 'synthetic.tmp').write_text('synthetic')
while not (root / 'release-worker').exists():
    time.sleep(.01)
if mode in ('timeout', 'cancel'):
    time.sleep(60)
if mode == 'success':
    target = root / 'config/switch_task.conf'
    temporary = target.with_name(target.name + '.tmp.' + str(os.getpid()))
    temporary.write_text('task=' + task + '\\nstate=success\\n')
    os.replace(temporary, target)
os._exit(7 if mode == 'failure' else 0)
'''


def wait_supervisor(scope, owner, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        require(scope.boot_id() == owner['boot'], 'Boot changed while waiting for supervisor')
        # This exact supervisor is adopted by the harness subreaper. Never infer
        # completion merely from disappearance of a helper-owned sidecar.
        try:
            pid, status = os.waitpid(owner['pid'], os.WNOHANG)
        except ChildProcessError as error:
            raise RuntimeError('Supervisor was not adopted/reaped by this harness') from error
        if pid:
            return os.waitstatus_to_exitcode(status)
        require(same_identity(scope, owner), 'Supervisor PID identity changed before waitpid')
        time.sleep(.05)
    raise RuntimeError('Supervisor did not exit within bounded cleanup deadline')


def assert_empty(scope, data, records, case, phase):
    require(scope.boot_id() == data['boot'], 'Boot changed during cleanup verification')
    members = scope.token_members(data['token'], data['owner']['start'], scope.snapshot())
    alive = [record for record in records if same_identity(scope, record)]
    case[phase] = {'token_members': members, 'recorded_alive_including_zombies': alive}
    require(not members and not alive, 'Owned process or zombie remains at ' + phase)


def cleanup_failed_case(scope, helper, env, pidfile, task, data, records):
    """Bounded, identity-scoped emergency cleanup; never signals a process name."""
    errors = []
    try:
        stopped = subprocess.run([sys.executable, str(helper), 'stop', str(pidfile), task],
                                 env=env, timeout=15, capture_output=True, text=True)
        if stopped.returncode:
            errors.append('Helper stop exit ' + str(stopped.returncode))
    except (OSError, subprocess.TimeoutExpired) as error:
        errors.append('Helper stop: ' + str(error))
    # A broken helper may leave its supervisor alive. It is our adopted child;
    # terminate only recorded identities, then reap newly adopted descendants.
    if data and scope.boot_id() == data['boot']:
        known = {(r['pid'], r['start']): r for r in records}
        known[(data['owner']['pid'], data['owner']['start'])] = data['owner']
        deadline = time.monotonic() + 6
        while time.monotonic() < deadline:
            for member in scope.token_members(data['token'], data['owner']['start'], scope.snapshot()):
                known[(member['pid'], member['start'])] = member
            for record in list(known.values()):
                if scope.same_process(record, include_zombie=True):
                    scope.signal_process(record, signal.SIGKILL)
                try:
                    os.waitpid(record['pid'], os.WNOHANG)
                except ChildProcessError:
                    pass
            if not any(scope.same_process(r, include_zombie=True) for r in known.values()):
                break
            time.sleep(.05)
        remaining = [r for r in known.values() if scope.same_process(r, include_zombie=True)]
        if remaining:
            errors.append('Emergency cleanup left identities: ' + json.dumps(remaining))
    return errors


def run_cases(scope, helper, root, report):
    """Exercise the real helper. Caller owns Android qualification or HOST_ONLY label."""
    scope.subreaper()
    report['harness_subreaper'] = {'pid': os.getpid(), 'boot': scope.boot_id()}
    expected_exits = {'success': 0, 'failure': 7, 'timeout': 124, 'cancel': 143}
    for mode, expected_exit in expected_exits.items():
        module = root / mode
        config = module / 'config'
        config.mkdir(parents=True)
        pidfile = config / 'switch_task_worker.pid'
        task = 'android-gate-' + mode
        env = dict(os.environ, MODDIR=str(module), TMPDIR=str(module),
                   LUOSHU_TASK_TIMEOUT_SECONDS='5' if mode == 'timeout' else '30')
        # The sentinel intentionally shares argv/task text, but never scope authority.
        for key in ('LUOSHU_TASK_SCOPE', 'LUOSHU_TASK_OWNER_PID', 'LUOSHU_TASK_OWNER_START',
                    'LUOSHU_TASK_PID_FILE', 'LUOSHU_TASK_WORK_DIR'):
            env.pop(key, None)
        (config / 'switch_task.conf').write_text('task=' + task + '\nstate=running\n')
        sentinel = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(90)', task], env=env)
        sentinel_identity = identity(scope, scope.proc_info(sentinel.pid), scope.boot_id())
        case = {'mode': mode, 'result': 'FAIL', 'sentinel': sentinel_identity,
                'expected_supervisor_exit': expected_exit}
        report['cases'].append(case)
        data = None
        records = []
        try:
            subprocess.run([sys.executable, str(helper), 'launch', str(pidfile), task,
                            str(module / 'task.log'), '--', sys.executable, '-c', fixture_code(module, task, mode)],
                           env=env, check=True, timeout=15)
            data = wait_for(lambda: scope.load_identity(pidfile))
            require(data['task'] == task, 'Supervisor task identity mismatch')
            owner = identity(scope, data['owner'], data['boot'], data['token'])
            worker = wait_for(lambda: read_json(module / 'worker.json'))
            leaf = wait_for(lambda: read_json(module / 'leaf.json'))
            intermediate = wait_for(lambda: read_json(module / 'intermediate.json'))
            require(intermediate['boot'] == data['boot'] and intermediate['token'] == data['token'],
                    'Double-fork intermediate identity does not belong to this scope')
            for record in (worker, leaf):
                require(record['boot'] == data['boot'] and record['token'] == data['token'],
                        'Fixture process does not belong to this exact scope')
                require(same_identity(scope, record), 'Fixture process ended before mode was exercised')
            require(scope.proc_info(owner['pid'])['ppid'] == os.getpid(),
                    'Detached supervisor was not adopted by harness subreaper')
            records = [owner, worker, intermediate, leaf]
            case.update(supervisor=owner, worker=worker, owned_leaf=leaf,
                        double_fork_intermediate=intermediate,
                        scope_identity=data, token_members_before=scope.token_members(
                            data['token'], owner['start'], scope.snapshot()))
            (module / 'release-worker').write_text('go\n')
            if mode == 'cancel':
                subprocess.run([sys.executable, str(helper), 'stop', str(pidfile), task],
                               env=env, check=True, timeout=15)
            actual_exit = wait_supervisor(scope, owner)
            case['supervisor_exit'] = actual_exit
            require(actual_exit == expected_exit,
                    'Wrong supervisor exit: expected %s, got %s' % (expected_exit, actual_exit))
            late = read_json(module / 'late-leaf.json')
            require(late and late['token'] == data['token'] and late['boot'] == data['boot'],
                    'TERM-time detached late fork was not observed')
            records.append(late)
            case['late_fork'] = late
            state = scope.state_values(config / 'switch_task.conf')
            case['terminal_state'] = state
            require(state.get('task') == task, 'Terminal task identity changed')
            require(state.get('state') == ('success' if mode == 'success' else 'failed'),
                    'Incorrect published terminal state for ' + mode)
            if mode == 'timeout':
                require('执行超时' in state.get('message', ''), 'Timeout state not published')
            if mode == 'cancel':
                require('已取消' in state.get('message', ''), 'Cancellation state not published')
            require(not Path(str(pidfile) + '.identity').exists(), 'Owned identity sidecar remains')
            require(not list((module / 'cache/tasks').glob('*')), 'Owned task workspace remains')
            assert_empty(scope, data, records, case, 'immediate_cleanup')
            require(scope.same_process(sentinel_identity), 'Independent sentinel killed or replaced')
            time.sleep(1)
            assert_empty(scope, data, records, case, 'delayed_cleanup')
            require(scope.same_process(sentinel_identity), 'Sentinel did not survive delayed check')
            case['result'] = 'PASS'
        except Exception as error:
            case['error'] = str(error)
            raise
        finally:
            try:
                if case['result'] != 'PASS':
                    data = data or scope.load_identity(pidfile)
                    case['emergency_cleanup_errors'] = cleanup_failed_case(
                        scope, helper, env, pidfile, task, data, records)
                case['task_log'] = scope.read(module / 'task.log')
            finally:
                if sentinel.poll() is None:
                    sentinel.terminate()
                try:
                    sentinel.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    sentinel.kill()
                    sentinel.wait(timeout=5)


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
        require(report['selinux'] == 'Enforcing', 'SELinux Enforcing required')
        with tempfile.TemporaryDirectory(prefix='luoshu-task-gate-', dir='/data/local/tmp') as temp:
            run_cases(scope, args.helper.resolve(), Path(temp), report)
        report['result'] = 'PASS'
    except Exception as error:
        report['error'] = str(error)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
    return 0 if report['result'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
