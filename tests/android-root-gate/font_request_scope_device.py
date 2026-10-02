#!/usr/bin/env python3
"""Real Android request-lease/process-cleanup gate; never substitutes a host pass.

The CLI requires a disposable rooted Enforcing AVD and the shipped interpreter.
run_cases is separately callable for explicitly labelled HOST_ONLY smoke tests.
Only synthetic workers, one independent sentinel, and private test files are used.
"""
import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import tempfile
import time


PREFIX = '[font-request] '
CASES = (
    ('success', 0, 'success', None),
    ('failure', 7, 'worker-error', None),
    ('timeout', 124, 'timeout', None),
    ('cancel', 143, 'cancel', signal.SIGTERM),
    ('cancel_int', 130, 'cancel', signal.SIGINT),
    ('cancel_hup', 129, 'cancel', signal.SIGHUP),
    ('stdin_eof', 130, 'client-disconnect', None),
    ('writer_death', 130, 'client-disconnect', None),
)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


def wait_for(check, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = check()
        if value:
            return value
        time.sleep(.05)
    raise RuntimeError('Request fixture did not become ready before deadline')


def events(path):
    try:
        lines = Path(path).read_text().splitlines()
    except OSError:
        return []
    result = []
    for line in lines:
        if line.startswith(PREFIX):
            try:
                value = json.loads(line[len(PREFIX):])
            except ValueError:
                continue
            if isinstance(value, dict):
                result.append(value)
    return result


def fixture_code(root, mode):
    return f'''
import json, os, signal, stat, time
from pathlib import Path
root = Path({str(root)!r})
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
stdin_stat = os.fstat(0)
stdin_is_devnull = (stat.S_ISCHR(stdin_stat.st_mode) and
                   stdin_stat.st_rdev == os.stat(os.devnull).st_rdev and os.read(0, 1) == b'')
try:
    private_stat = os.fstat(int(os.environ['LUOSHU_GATE_PRIVATE_FD']))
    private_fd_not_inherited = (private_stat.st_dev != int(os.environ['LUOSHU_GATE_PRIVATE_DEV']) or
                                private_stat.st_ino != int(os.environ['LUOSHU_GATE_PRIVATE_INO']))
except OSError:
    private_fd_not_inherited = True
publish('stdin.json', {{'is_devnull': stdin_is_devnull,
                       'target': os.readlink('/proc/self/fd/0'),
                       'private_fd_not_inherited': private_fd_not_inherited}})
if not stdin_is_devnull:
    os._exit(91)
if not private_fd_not_inherited:
    os._exit(92)
print(json.dumps({{'fixture': 'font-request', 'mode': mode, 'stdin_is_devnull': True}},
                 separators=(',', ':')), flush=True)
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
while not (root / 'release-worker').exists():
    time.sleep(.01)
if mode not in ('success', 'failure'):
    time.sleep(90)
os._exit(7 if mode == 'failure' else 0)
'''


def same_identity(scope, record):
    return (scope.boot_id() == record['boot'] and
            scope.same_process(record, include_zombie=True))


def observe_empty(scope, started, records, directory):
    require(scope.boot_id() == started['boot'], 'Boot changed during request verification')
    return {
        'token_members': scope.token_members(started['token'], started['owner']['start'], scope.snapshot()),
        'recorded_alive_including_zombies': [r for r in records if same_identity(scope, r)],
        'scope_directory_entries': sorted(p.name for p in directory.iterdir()),
    }


def assert_empty(scope, started, records, directory, case, label):
    observation = observe_empty(scope, started, records, directory)
    case[label] = observation
    require(not any(observation.values()), 'Request ownership cleanup incomplete at ' + label)


def stop_direct(process):
    if process is None:
        return
    if process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def emergency_cleanup(scope, process, started, records):
    """Only this direct child and recorded/adopted token identities are targets."""
    errors = []
    try:
        stop_direct(process)
    except (OSError, subprocess.TimeoutExpired) as error:
        errors.append(str(error))
    if not started or scope.boot_id() != started['boot']:
        return errors
    known = {(r['pid'], r['start']): r for r in records}
    deadline = time.monotonic() + 6
    while time.monotonic() < deadline:
        for member in scope.token_members(started['token'], started['owner']['start'], scope.snapshot()):
            known[(member['pid'], member['start'])] = member
        for record in list(known.values()):
            if scope.same_process(record, include_zombie=True):
                scope.signal_process(record, signal.SIGKILL)
            # The harness subreaper adopts surviving descendants on supervisor exit.
            try:
                os.waitpid(record['pid'], os.WNOHANG)
            except ChildProcessError:
                pass
        remaining = [r for r in known.values() if scope.same_process(r, include_zombie=True)]
        if not remaining:
            return errors
        time.sleep(.05)
    errors.append('Owned identities remain after emergency cleanup: ' + json.dumps(remaining))
    return errors


def run_cases(scope, helper, root, report):
    """Caller must label host testing; this does not perform Android qualification."""
    scope.subreaper()
    boot = scope.boot_id()
    require(boot, 'Missing kernel boot identity')
    report['harness_subreaper'] = {'pid': os.getpid(), 'boot': boot}
    report['request_helper_sha256'] = hashlib.sha256(helper.read_bytes()).hexdigest()
    env = dict(os.environ)
    for key in ('LUOSHU_TASK_SCOPE', 'LUOSHU_TASK_OWNER_PID', 'LUOSHU_TASK_OWNER_START',
                'LUOSHU_TASK_PID_FILE', 'LUOSHU_TASK_WORK_DIR'):
        env.pop(key, None)
    for mode, expected_code, expected_reason, cancel_signal in CASES:
        case_root = root / mode
        case_root.mkdir(mode=0o700)
        directory = case_root / 'request-scopes'
        out_path, err_path = case_root / 'stdout.log', case_root / 'stderr.log'
        case = {'mode': mode, 'result': 'FAIL', 'expected_exit': expected_code,
                'expected_reason': expected_reason, 'caller_lease': 'open pipe writer'}
        report['cases'].append(case)
        process = writer = sentinel = None
        read_fd = write_fd = private_fd = None
        started = None
        records = []
        with out_path.open('wb') as stdout, err_path.open('wb') as stderr:
            try:
                sentinel = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)', mode], env=env)
                sentinel_id = dict(scope.proc_info(sentinel.pid), boot=boot)
                case['sentinel'] = sentinel_id
                read_fd, write_fd = os.pipe()
                if mode == 'writer_death':
                    # This process becomes the SOLE writer. Killing it must close
                    # the lease without an explicit close by the harness/client.
                    writer = subprocess.Popen([sys.executable, '-c',
                        'import os,sys,time; os.fstat(int(sys.argv[1])); time.sleep(120)', str(write_fd)],
                        pass_fds=(write_fd,), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL, env=env)
                    case['client_writer'] = dict(scope.proc_info(writer.pid), boot=boot)
                command = [sys.executable, str(helper), '--scope-dir', str(directory),
                           '--timeout', '8' if mode == 'timeout' else '45', '--',
                           sys.executable, '-c', fixture_code(case_root, mode)]
                private_fd = os.open(case_root / 'supervisor-only-fd', os.O_CREAT | os.O_RDWR, 0o600)
                private_stat = os.fstat(private_fd)
                request_env = dict(env, LUOSHU_GATE_PRIVATE_FD=str(private_fd),
                                   LUOSHU_GATE_PRIVATE_DEV=str(private_stat.st_dev),
                                   LUOSHU_GATE_PRIVATE_INO=str(private_stat.st_ino))
                process = subprocess.Popen(command, stdin=read_fd, stdout=stdout, stderr=stderr,
                                           close_fds=True, pass_fds=(private_fd,), env=request_env)
                os.close(read_fd)
                read_fd = None
                if writer is not None:
                    os.close(write_fd)
                    write_fd = None
                started = wait_for(lambda: next((e for e in events(err_path) if e.get('event') == 'started'), None))
                require(started['boot'] == boot and started['owner']['pid'] == process.pid,
                        'Started event does not identify this exact supervisor/boot')
                require(isinstance(started['token'], str) and len(started['token']) == 32 and
                        all(c in '0123456789abcdef' for c in started['token']), 'Invalid request scope token')
                owner = dict(started['owner'], boot=boot, token=started['token'])
                require(same_identity(scope, owner), 'Supervisor identity is no longer live at admission')
                worker = wait_for(lambda: read_json(case_root / 'worker.json'))
                leaf = wait_for(lambda: read_json(case_root / 'leaf.json'))
                intermediate = wait_for(lambda: read_json(case_root / 'intermediate.json'))
                for record in (worker, leaf, intermediate):
                    require(record['boot'] == boot and record['token'] == started['token'],
                            'Fixture process does not belong to this request')
                require(started['worker'] == worker['pid'], 'Started worker PID mismatch')
                require(same_identity(scope, worker) and same_identity(scope, leaf),
                        'Worker/leaf exited before the requested case was exercised')
                case['worker_stdin'] = wait_for(lambda: read_json(case_root / 'stdin.json'))
                require(case['worker_stdin']['is_devnull'], 'Worker inherited caller stdin lease')
                require(case['worker_stdin']['private_fd_not_inherited'], 'Worker inherited supervisor-only FD')
                records = [owner, worker, intermediate, leaf]
                case.update(started=started, identities=list(records), token_members_before=scope.token_members(
                    started['token'], owner['start'], scope.snapshot()))
                pidfile = directory / (started['token'] + '.pid')
                identity_data = scope.load_identity(pidfile)
                require(identity_data and identity_data['token'] == started['token'] and
                        identity_data['owner']['start'] == owner['start'], 'Private sidecar identity mismatch')
                case['scope_identity'] = identity_data
                require(stat.S_IMODE(directory.stat().st_mode) == 0o700, 'Request scope directory is not private')
                (case_root / 'release-worker').write_text('go\n')
                if cancel_signal is not None:
                    require(scope.same_process(owner), 'Supervisor disappeared before cancellation')
                    process.send_signal(cancel_signal)
                elif mode == 'stdin_eof':
                    os.close(write_fd)
                    write_fd = None
                    case['caller_lease'] = 'writer explicitly closed after fixture admission'
                elif mode == 'writer_death':
                    require(writer.poll() is None and scope.same_process(case['client_writer']),
                            'Client writer died before the requested death stimulus')
                    writer.kill()
                    case['client_writer_exit'] = writer.wait(timeout=5)
                    require(case['client_writer_exit'] == -signal.SIGKILL, 'Client writer death was not observed')
                    records.append(case['client_writer'])
                    case['caller_lease'] = 'sole writer process killed; harness has no write descriptor'
                # Popen.wait owns this direct supervisor's waitpid. No communicate(),
                # which could close a pipe and accidentally turn every case into EOF.
                code = process.wait(timeout=30)
                case['supervisor_exit'] = code
                case['events'] = events(err_path)
                begins = [e for e in case['events'] if e.get('event') == 'started']
                finishes = [e for e in case['events'] if e.get('event') == 'finished']
                require(len(begins) == len(finishes) == 1, 'Missing or duplicate request lifecycle events')
                finished = finishes[0]
                case['finished'] = finished
                require(finished['token'] == started['token'], 'Finished token mismatch')
                require(type(finished.get('code')) is int, 'Completion code is not an integer')
                require(type(finished.get('elapsed_ms')) in (int, float) and
                        math.isfinite(finished['elapsed_ms']) and finished['elapsed_ms'] >= 0,
                        'Invalid elapsed timing evidence')
                require(code == expected_code and finished['code'] == expected_code,
                        'Wrong request exit: expected %s, got process=%s event=%s' %
                        (expected_code, code, finished.get('code')))
                require(finished['reason'] == expected_reason and finished['cleaned'] is True,
                        'Wrong completion reason or unproven cleanup')
                late = read_json(case_root / 'late-leaf.json')
                require(late and late['boot'] == boot and late['token'] == started['token'],
                        'No actual TERM-time detached late fork was observed')
                records.append(late)
                case['identities'] = list(records)
                case['late_fork'] = late
                expected_stdout = json.dumps({'fixture': 'font-request', 'mode': mode,
                                              'stdin_is_devnull': True}, separators=(',', ':')) + '\n'
                case['stdout'] = out_path.read_text()
                require(case['stdout'] == expected_stdout, 'Supervisor polluted or lost worker stdout protocol')
                assert_empty(scope, started, records, directory, case, 'immediate_cleanup')
                require(scope.same_process(sentinel_id), 'Independent sentinel killed/replaced')
                time.sleep(1)
                assert_empty(scope, started, records, directory, case, 'delayed_cleanup')
                require(scope.same_process(sentinel_id), 'Sentinel did not survive delayed verification')
                case['result'] = 'PASS'
            except Exception as error:
                case['error'] = str(error)
                raise
            finally:
                for fd in (read_fd, write_fd, private_fd):
                    if fd is not None:
                        os.close(fd)
                try:
                    if case['result'] != 'PASS':
                        # Collect records even if startup failed midway through admission.
                        for name in ('worker.json', 'intermediate.json', 'leaf.json', 'late-leaf.json'):
                            record = read_json(case_root / name)
                            if record and started and record.get('token') == started['token']:
                                records.append(record)
                        case['emergency_cleanup_errors'] = emergency_cleanup(scope, process, started, records)
                    case['stderr'] = err_path.read_text()
                    case.setdefault('stdout', out_path.read_text())
                    case['scope_entries_after'] = sorted(p.name for p in directory.iterdir()) if directory.exists() else []
                finally:
                    stop_direct(writer)
                    stop_direct(sentinel)
    require(hashlib.sha256(helper.read_bytes()).hexdigest() == report['request_helper_sha256'],
            'Request helper changed during this run')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--helper', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    report = {'result': 'FAIL', 'scope': 'font request helper; not full App/module delivery', 'cases': []}
    try:
        require(Path('/system/bin/getprop').exists(), 'Android runtime required')
        require(subprocess.check_output(['/system/bin/getprop', 'ro.kernel.qemu']).strip() == b'1',
                'Disposable AVD required')
        require(os.getuid() == 0, 'Root required')
        report['selinux'] = subprocess.check_output(['/system/bin/getenforce'], text=True).strip()
        require(report['selinux'] == 'Enforcing', 'SELinux Enforcing required')
        helper = args.helper.resolve()
        task_helper = helper.with_name('task_scope.py')
        sys.dont_write_bytecode = True
        spec = importlib.util.spec_from_file_location('request_scope_verifier', task_helper)
        scope = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(scope)
        report['task_helper_sha256'] = hashlib.sha256(task_helper.read_bytes()).hexdigest()
        report['environment'] = 'ACTUAL_ANDROID_QEMU_ROOT_ENFORCING'
        with tempfile.TemporaryDirectory(prefix='luoshu-request-gate-', dir='/data/local/tmp') as temp:
            run_cases(scope, helper, Path(temp), report)
        report['result'] = 'PASS'
    except Exception as error:
        report['error'] = str(error)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report['result'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
