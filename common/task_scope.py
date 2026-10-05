#!/usr/bin/env python3
"""Bounded, single-task Linux subreaper. Never signal processes by name/group."""
import argparse
import ctypes
import errno
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time


BOOT = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
SELF_PROC = int(os.readlink('/proc/self'))
SELF_NS = os.readlink('/proc/self/ns/pid')
TOKEN = re.compile(r'[A-Za-z0-9_.-]{1,160}\Z')


def identity(proc_pid):
    try:
        root = Path('/proc') / str(proc_pid)
        fields = (root / 'stat').read_text().rsplit(') ', 1)[1].split()
        namespace = os.readlink(root / 'ns/pid')
        if namespace != SELF_NS:
            return None
        local_pid = int(proc_pid)
        for line in (root / 'status').read_text().splitlines():
            if line.startswith('NSpid:'):
                local_pid = int(line.split()[-1])
                break
        return {'procPid': int(proc_pid), 'pid': local_pid, 'parent': int(fields[1]),
                'start': fields[19], 'state': fields[0], 'namespace': namespace, 'boot': BOOT}
    except (OSError, ValueError, IndexError, TypeError):
        return None


def atomic(path, value):
    path = Path(path)
    tmp = path.with_name(path.name + '.tmp.' + str(os.getpid()))
    try:
        with tmp.open('w') as output:
            os.chmod(tmp, 0o600)
            output.write(value)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def read_owner(pidfile):
    try:
        record = json.loads(Path(str(pidfile) + '.owner.json').read_text())
        for suffix, key in (('', 'pid'), ('.task', 'task'), ('.start', 'start'), ('.boot', 'boot')):
            if Path(str(pidfile) + suffix).read_text().strip() != str(record[key]):
                return None
        return record
    except (OSError, ValueError, KeyError, TypeError):
        return None


def same_process(record):
    if not record or record.get('boot') != BOOT or record.get('namespace') != SELF_NS:
        return False
    current = identity(record.get('procPid'))
    return bool(current and current['state'] != 'Z' and
                all(current[key] == record.get(key) for key in ('pid', 'start', 'namespace', 'boot')))


def signal_record(record, number):
    if not same_process(record):
        return False
    # pidfd closes the last start-time-check / kill race where supported.
    descriptor = None
    try:
        if hasattr(os, 'pidfd_open') and hasattr(signal, 'pidfd_send_signal'):
            try:
                descriptor = os.pidfd_open(record['pid'])
            except OSError as error:
                if error.errno not in (errno.ENOSYS, errno.EINVAL, errno.ENOTSUP):
                    raise
            if descriptor is not None:
                if not same_process(record):
                    return False
                signal.pidfd_send_signal(descriptor, number)
        if descriptor is None:
            if not same_process(record):
                return False
            os.kill(record['pid'], number)
        return True
    except OSError:
        return False
    finally:
        if descriptor is not None:
            os.close(descriptor)


def process_tree(roots, excluded=()):
    records = {}
    for entry in Path('/proc').iterdir():
        if entry.name.isdigit():
            record = identity(int(entry.name))
            if record:
                records[record['procPid']] = record
    parents = set(roots)
    excluded = set(excluded)
    owned = {}
    changed = True
    while changed:
        changed = False
        for pid, record in records.items():
            if pid not in parents and pid not in excluded and record['parent'] in parents:
                parents.add(pid)
                owned[pid] = record
                changed = True
    return owned


def descendants(excluded=()):
    return process_tree([SELF_PROC], excluded)


def reap(worker):
    count = 0
    while True:
        try:
            pid, status = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            break
        if pid == 0:
            break
        count += 1
        if worker is not None and pid == worker.pid:
            worker.returncode = os.waitstatus_to_exitcode(status)
    return count


def clear_owner(pidfile, record):
    if read_owner(pidfile) != record:
        return
    for suffix in ('', '.task', '.start', '.boot', '.ready', '.owner.json'):
        Path(str(pidfile) + suffix).unlink(missing_ok=True)


def registered_children(pidfile, seen=None):
    result = []
    seen = set() if seen is None else seen
    if str(pidfile) in seen:
        return result
    seen.add(str(pidfile))
    directory = Path(str(pidfile) + '.children')
    for path in directory.glob('*.json'):
        try:
            child = json.loads(path.read_text())
            if child == read_owner(child['pidfile']):
                result.append(child)
                result.extend(registered_children(child['pidfile'], seen))
        except (OSError, ValueError, KeyError, TypeError):
            pass
    return result


def remove_temporary(record):
    value = record.get('temporary')
    if not value:
        return
    path = Path(value)
    root = Path(os.environ.get('LUOSHU_TMP_DIR', str(Path(record['pidfile']).parent / 'tmp')))
    expected = 'task-' + record['task'] + '-' + str(record['pid']) + '-' + record['start']
    if path.name != expected or path.parent.resolve() != root.resolve() or path.is_symlink():
        raise RuntimeError('owned temporary identity mismatch')
    try:
        shutil.rmtree(path)
    except FileNotFoundError:
        pass


def cleanup(worker, pidfile, allow_handoff):
    # Only a successful request-start may explicitly hand a bounded supervisor
    # to the next task. Nested worker scopes cannot register further handoffs.
    children = registered_children(pidfile)
    handoffs = [child for child in children if allow_handoff and child.get('timeout', 0) > 0
                and child.get('handoff') and same_process(child)]
    excluded = [child['procPid'] for child in handoffs]
    started = time.monotonic()
    signalled = set()
    reaped = reap(worker)
    initial = descendants(excluded)
    root = next((r for r in initial.values() if worker and r['pid'] == worker.pid), None)
    cooperative = bool(root and worker.returncode is None)
    grace = 2.5 if cooperative else 0
    kill_after = 3.5 if cooperative else 1.8
    termed = set()
    if root:
        signal_record(root, signal.SIGTERM)
        termed.add((root['pid'], root['start']))
    while time.monotonic() - started < 5.0:
        reaped += reap(worker)
        owned = descendants(excluded)
        if not owned:
            break
        elapsed = time.monotonic() - started
        # Give worker EXIT/TERM handlers time to remove transaction temporaries.
        if elapsed >= grace or worker is None or worker.returncode is not None:
            number = signal.SIGTERM if elapsed < kill_after else signal.SIGKILL
            for record in owned.values():
                key = (record['pid'], record['start'])
                if number == signal.SIGTERM:
                    # Allow EXIT traps to finish their newly spawned rm/lock
                    # utilities. Initial children receive TERM only once;
                    # every remaining/new child still gets bounded KILL.
                    if record['procPid'] not in initial or key in termed:
                        continue
                    termed.add(key)
                if signal_record(record, number):
                    signalled.add((record['pid'], record['start']))
        time.sleep(.04)
    reaped += reap(worker)
    remaining = descendants(excluded)
    errors = []
    if not remaining:
        for child in children:
            if child not in handoffs and not same_process(child):
                try:
                    remove_temporary(child)
                except BaseException as error:
                    errors.append(str(error))
                    continue
                if read_owner(child['pidfile']) == child:
                    # An outer supervisor can reap a nested supervisor before
                    # its own finally block; publish the verified cleanup here.
                    report = dict(schema='task-cleanup-v2', task=child['task'], pid=child['pid'],
                                  start=child['start'], boot=child['boot'], namespace=child['namespace'], result=143,
                                  cleaned=True, reason='parent-cleanup', leftoverPids=[],
                                  handoffTasks=[], handoffOwners=[])
                    atomic(child['pidfile'] + '.cleanup.json', json.dumps(report, sort_keys=True) + '\n')
                clear_owner(child['pidfile'], child)
                child_directory = Path(child['pidfile'] + '.children')
                for path in child_directory.glob('*.json'):
                    path.unlink(missing_ok=True)
                try:
                    child_directory.rmdir()
                except OSError:
                    pass
    directory = Path(str(pidfile) + '.children')
    for path in directory.glob('*.json'):
        path.unlink(missing_ok=True)
    try:
        directory.rmdir()
    except OSError:
        pass
    return {'terminated': len(signalled), 'reaped': reaped,
            'leftoverPids': sorted(r['pid'] for r in remaining.values()),
            'handoffTasks': [r['task'] for r in handoffs], 'handoffOwners': handoffs, 'cleanupErrors': errors}


def run(args):
    if not TOKEN.fullmatch(args.task) or not 0.05 <= args.timeout <= 3600:
        return 2
    pidfile = Path(args.pid_file)
    pidfile.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = open(str(pidfile) + '.lock', 'a')
    os.chmod(str(pidfile) + '.lock', 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        return 3
    if same_process(read_owner(pidfile)):
        return 3
    # A dead supervisor does not prove that its adopted descendants exited.
    # Reconcile the exact prior registration while still holding its launch
    # lock, before replacing any identity or cleanup evidence.
    _, previous_code = cancel(pidfile, '')
    if previous_code:
        print('TASK-SCOPE: previous task cleanup is unconfirmed; task refused', file=sys.stderr)
        return previous_code
    Path(str(pidfile) + '.cleanup.json').unlink(missing_ok=True)
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(36, 1, 0, 0, 0) != 0:
        print('TASK-SCOPE: child subreaper unavailable; task refused', file=sys.stderr)
        return 126
    record = identity(SELF_PROC)
    if not record or record['pid'] != os.getpid():
        return 126
    parent = identity(record['parent']) if args.parent_watch else None
    record.update(task=args.task, pidfile=str(pidfile), timeout=args.timeout,
                  handoff=bool(os.environ.get('LUOSHU_SCOPE_ALLOW_HANDOFF') == '1'
                               and os.environ.get('LUOSHU_SCOPE_HANDOFF') == '1'))
    temporary_root = Path(os.environ.get('LUOSHU_TMP_DIR', str(pidfile.parent / 'tmp')))
    temporary = temporary_root / ('task-' + args.task + '-' + str(os.getpid()) + '-' + record['start'])
    record['temporary'] = str(temporary)
    interrupted = []
    for number in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
        signal.signal(number, lambda number, _frame: interrupted.append(number))
    worker = None
    result = 126
    started = time.monotonic()
    reason = 'launch-failed'
    published = False
    reaped_during_run = 0
    try:
        # Supervisor itself publishes identity before spawning any work.
        for suffix, key in (('.task', 'task'), ('.start', 'start'), ('.boot', 'boot')):
            atomic(str(pidfile) + suffix, str(record[key]) + '\n')
        atomic(str(pidfile) + '.owner.json', json.dumps(record, sort_keys=True))
        atomic(pidfile, str(record['pid']) + '\n')
        published = True
        outer = os.environ.get('LUOSHU_TASK_SCOPE_PIDFILE')
        if outer:
            child_dir = Path(outer + '.children')
            child_dir.mkdir(mode=0o700, exist_ok=True)
            atomic(child_dir / (str(os.getpid()) + '.json'), json.dumps(record, sort_keys=True))
        env = dict(os.environ, LUOSHU_TASK_SCOPE_PID=str(os.getpid()),
                   LUOSHU_TASK_SCOPE_PIDFILE=str(pidfile), LUOSHU_TASK_SCOPE_TASK=args.task,
                   LUOSHU_SCOPE_ALLOW_HANDOFF='1' if args.request else '0', LUOSHU_SCOPE_HANDOFF='0')
        temporary_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary.mkdir(mode=0o700)
        env['LUOSHU_TASK_SCOPE_TMPDIR'] = str(temporary)
        worker = subprocess.Popen(args.command, env=env, start_new_session=True)
        atomic(str(pidfile) + '.ready', args.task + '\n')
        reason = 'completed'
        while True:
            reaped_during_run += reap(worker)
            if interrupted:
                result = 128 + interrupted[0]
                reason = 'cancelled'
                break
            if parent and not same_process(parent):
                result = 129
                reason = 'parent-exited'
                break
            if time.monotonic() - started >= args.timeout:
                result = 124
                reason = 'timeout'
                break
            if worker.returncode is not None:
                result = worker.returncode if worker.returncode >= 0 else 128 - worker.returncode
                break
            time.sleep(.04)
    except BaseException as error:
        print('TASK-SCOPE: ' + str(error), file=sys.stderr)
    finally:
        try:
            proof = cleanup(worker, pidfile, args.request and reason == 'completed' and result == 0)
        except BaseException as error:
            proof = dict(terminated=0, reaped=0, leftoverPids=sorted(r['pid'] for r in descendants().values()),
                         handoffTasks=[], handoffOwners=[], cleanupErrors=[str(error)])
        proof['reaped'] += reaped_during_run
        if not proof['leftoverPids']:
            try:
                remove_temporary(record)
            except BaseException as error:
                proof['cleanupErrors'].append(str(error))
        if proof['leftoverPids'] or proof['cleanupErrors']:
            result = 125
        report = dict(schema='task-cleanup-v2', task=args.task, result=result, reason=reason,
                      cleaned=not proof['leftoverPids'] and not proof['cleanupErrors'], boot=BOOT, pid=record['pid'],
                      start=record['start'], namespace=SELF_NS, durationSeconds=round(time.monotonic() - started, 3), **proof)
        if published:
            atomic(str(pidfile) + '.cleanup.json', json.dumps(report, sort_keys=True) + '\n')
            if report['cleaned']:
                clear_owner(pidfile, record)
        print('TASK-CLEANUP ' + json.dumps(report, sort_keys=True), file=sys.stderr)
    return result


def cancel(pidfile, task):
    record = read_owner(pidfile)
    if record and task and record.get('task') != task:
        return {'status': 'error', 'data': {'task': task, 'cleaned': False}, 'message': '任务身份不匹配'}, 3
    task = task or (record.get('task', '') if record else '')
    if not same_process(record):
        # A full reboot ends every process belonging to that registration. Do
        # not require an EXIT proof from a supervisor killed by the old boot.
        previous_boot = bool(record and record.get('boot') and record['boot'] != BOOT)
        if previous_boot:
            clear_owner(pidfile, record)
            return {'status': 'ok', 'data': {'task': task, 'token': task,
                    'cleaned': True, 'state': 'previous-boot'}}, 0
        clean = False
        try:
            proof = json.loads(Path(str(pidfile) + '.cleanup.json').read_text())
            if not isinstance(proof, dict):
                raise ValueError('invalid cleanup proof')
            task = task or proof.get('task', '')
            clean = (proof.get('task') == task and proof.get('boot') == BOOT and
                     proof.get('namespace', SELF_NS) == SELF_NS and
                     proof.get('cleaned') is True and not proof.get('leftoverPids') and not proof.get('cleanupErrors'))
            if record:
                clean = clean and record.get('namespace') == SELF_NS and \
                        all(proof.get(key) == record.get(key) for key in ('task', 'pid', 'start', 'boot'))
            elif Path(str(pidfile) + '.owner.json').exists():
                clean = False
            elif any(Path(str(pidfile) + suffix).exists() for suffix in ('', '.task', '.start', '.boot', '.ready')):
                clean = False
            elif proof.get('boot') and proof['boot'] != BOOT:
                clean = proof.get('task') == task
            # The submission may have finished just before App cancellation,
            # before its response/task id reached the caller.
            if clean:
                for child in proof.get('handoffOwners', []):
                    if read_owner(child['pidfile']) == child:
                        _, code = cancel(child['pidfile'], child['task'])
                        clean = clean and code == 0
        except FileNotFoundError:
            # Fresh slots have no registration. Legacy sidecars may be safely
            # retired only when their boot identity predates this boot.
            evidence = [Path(str(pidfile) + suffix) for suffix in ('', '.owner.json', '.task', '.start', '.boot', '.ready')]
            clean = not any(path.exists() for path in evidence)
            if not clean and record is None and not Path(str(pidfile) + '.owner.json').exists():
                try:
                    saved_boot = Path(str(pidfile) + '.boot').read_text().strip()
                    clean = bool(saved_boot and saved_boot != BOOT)
                    if clean:
                        for path in evidence:
                            path.unlink(missing_ok=True)
                except OSError:
                    pass
        except (OSError, ValueError, KeyError, TypeError):
            clean = False
        if record and clean:
            clear_owner(pidfile, record)
        return {'status': 'ok' if clean else 'error', 'data': {'task': task or '',
                'token': task or '', 'cleaned': clean, 'state': 'absent' if clean else 'cleanup-unknown'}}, 0 if clean else 125
    signal_record(record, signal.SIGTERM)
    deadline = time.monotonic() + 7
    while same_process(record) and time.monotonic() < deadline:
        time.sleep(.04)
    try:
        proof = json.loads(Path(str(pidfile) + '.cleanup.json').read_text())
        if not isinstance(proof, dict):
            raise ValueError('invalid cleanup proof')
        clean = (not same_process(record) and proof.get('cleaned') is True and
                 proof.get('namespace', SELF_NS) == SELF_NS and
                 not proof.get('leftoverPids') and not proof.get('cleanupErrors') and
                 all(proof.get(key) == record.get(key) for key in ('task', 'pid', 'start', 'boot')))
        for child in proof.get('handoffOwners', []):
            if read_owner(child['pidfile']) == child:
                _, code = cancel(child['pidfile'], child['task'])
                clean = clean and code == 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        clean = False
    return {'status': 'ok' if clean else 'error', 'data': {'task': record['task'], 'token': record['task'],
            'cleaned': clean, 'state': 'cancelled' if clean else 'cleanup-failed'}}, 0 if clean else 125


def cleaned(pidfile, task):
    try:
        proof = json.loads(Path(str(pidfile) + '.cleanup.json').read_text())
        record = read_owner(pidfile)
        return bool(proof.get('cleaned') is True and not proof.get('leftoverPids') and not proof.get('cleanupErrors') and
                    proof.get('task') == task and proof.get('boot') == BOOT and proof.get('namespace', SELF_NS) == SELF_NS and
                    not same_process(record) and
                    (record or not Path(str(pidfile) + '.owner.json').exists()) and
                    (not record or record.get('namespace') == SELF_NS and
                     all(proof.get(key) == record.get(key) for key in ('task', 'pid', 'start', 'boot'))))
    except (OSError, ValueError, TypeError, AttributeError):
        return False


def settled(pidfile):
    """Read-only slot inspection: cleanup proof, safe absence, or old boot."""
    record = read_owner(pidfile)
    if same_process(record):
        return 3
    if record and record.get('boot') and record['boot'] != BOOT:
        return 0
    if not record:
        if Path(str(pidfile) + '.owner.json').exists():
            return 125
        if any(Path(str(pidfile) + suffix).exists() for suffix in ('', '.task', '.start', '.boot', '.ready')):
            try:
                saved_boot = Path(str(pidfile) + '.boot').read_text().strip()
                return 0 if saved_boot and saved_boot != BOOT else 125
            except OSError:
                return 125
    proof_path = Path(str(pidfile) + '.cleanup.json')
    if not proof_path.exists():
        return 125 if record else 0
    try:
        proof = json.loads(proof_path.read_text())
        if not isinstance(proof, dict):
            return 125
        if not record and proof.get('boot') and proof['boot'] != BOOT:
            return 0
        if not cleaned(pidfile, record['task'] if record else proof.get('task', '')):
            return 125
        for child in proof.get('handoffOwners', []):
            if read_owner(child['pidfile']) == child:
                if same_process(child):
                    return 3
                if child.get('boot') == BOOT and not cleaned(child['pidfile'], child['task']):
                    return 125
        return 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return 125


def legacy_cancel(pidfile, module):
    """Migration only: snapshot live identity after exact old command proof.

    An old version was not a subreaper. Already escaped historical orphans
    cannot be identified from its PID file and are never killed by name.
    """
    pidfile = Path(pidfile)
    try:
        pid_text = pidfile.read_text().strip()
        if not pid_text:
            return 0
        pid = int(pid_text.splitlines()[0])
    except OSError:
        return 0
    except (ValueError, IndexError):
        return 125
    if pid <= 1:
        return 125
    record = None
    for entry in Path('/proc').iterdir():
        if entry.name.isdigit():
            candidate = identity(int(entry.name))
            if candidate and candidate['pid'] == pid:
                record = candidate
                break
    if not record or record['state'] == 'Z':
        for suffix in ('', '.task', '.boot', '.start'):
            Path(str(pidfile) + suffix).unlink(missing_ok=True)
        return 0
    try:
        saved_boot = Path(str(pidfile) + '.boot').read_text().strip()
    except OSError:
        lock_props = dict(line.split('=', 1) for line in pid_text.splitlines()[1:] if '=' in line)
        saved_boot = lock_props.get('boot_id', lock_props.get('bootId', ''))
        try:
            saved_boot = saved_boot or (pidfile.parent / 'boot-id').read_text().strip()
        except OSError:
            return 125
    if saved_boot != BOOT:
        for suffix in ('', '.task', '.boot', '.start'):
            Path(str(pidfile) + suffix).unlink(missing_ok=True)
        return 0
    lock_start = dict(line.split('=', 1) for line in pid_text.splitlines()[1:] if '=' in line).get('starttime')
    if lock_start and lock_start != record['start']:
        return 125
    try:
        command = Path('/proc', str(record['procPid']), 'cmdline').read_bytes().decode().split('\0')
        task = Path(str(pidfile) + '.task').read_text().strip()
    except OSError:
        task = ''
        command = Path('/proc', str(record['procPid']), 'cmdline').read_bytes().decode().split('\0')
    owned_script = [arg for arg in command if arg.startswith(str(module) + '/common/')
                    or arg.startswith(str(module) + '/system/bin/')]
    singleton = pidfile.parent.name == '.google-font-provider.lock' and pidfile.name == 'pid'
    script_task = task in ('font_switch_safe.sh', 'google_font_provider_service.sh') and any(
        Path(arg).name == task for arg in owned_script)
    if not owned_script or not (task and (task in command or script_task) or singleton and any(
            Path(arg).name == 'google_font_provider_service.sh' for arg in owned_script)):
        return 125
    saved = {record['procPid']: record, **process_tree([record['procPid']])}
    started = time.monotonic()
    signal_record(record, signal.SIGTERM)
    while time.monotonic() - started < 4:
        roots = [proc_pid for proc_pid, value in saved.items() if same_process(value)]
        saved.update(process_tree(roots))
        live = [value for value in saved.values() if same_process(value)]
        if not live:
            break
        if time.monotonic() - started > .5:
            number = signal.SIGTERM if time.monotonic() - started < 1.8 else signal.SIGKILL
            for value in live:
                signal_record(value, number)
        time.sleep(.04)
    remaining = [value['pid'] for value in saved.values() if same_process(value)]
    report = dict(schema='legacy-observed-tree-v1', task=task, pid=pid, start=record['start'],
                  boot=BOOT, cleaned=not remaining, leftoverPids=remaining,
                  ownershipProof='boot-exact-command-live-start')
    try:
        atomic(str(pidfile) + '.cleanup.json', json.dumps(report, sort_keys=True) + '\n')
    except FileNotFoundError:
        # Old provider EXIT handlers may release the entire singleton folder.
        # Do not recreate it after a verified successful shutdown.
        pass
    try:
        current_text = pidfile.read_text().strip()
    except FileNotFoundError:
        current_text = None
    if not remaining and current_text == pid_text:
        for suffix in ('', '.task', '.boot', '.start'):
            Path(str(pidfile) + suffix).unlink(missing_ok=True)
    print(json.dumps({'status': 'ok' if not remaining else 'error', 'data': report}, separators=(',', ':')))
    return 0 if not remaining else 125


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest='action', required=True)
    runner = commands.add_parser('run')
    runner.add_argument('--pid-file', required=True)
    runner.add_argument('--task', required=True)
    runner.add_argument('--timeout', type=float, default=360)
    runner.add_argument('--parent-watch', action='store_true')
    runner.add_argument('--request', action='store_true')
    runner.add_argument('command', nargs=argparse.REMAINDER)
    for name in ('alive', 'cancel', 'cleaned', 'settled'):
        child = commands.add_parser(name)
        child.add_argument('pidfile')
        child.add_argument('task', nargs='?', default='')
    stop_all = commands.add_parser('cancel-all')
    stop_all.add_argument('module')
    args = parser.parse_args()
    if args.action == 'cancel-all':
        module = Path(args.module).resolve()
        roots = [module / '.luoshu-state/tasks', module / '.luoshu-state/config', module / 'config']
        seen = set()
        result = 0
        for root in roots:
            if root.is_dir():
                if not root.resolve().is_relative_to(module):
                    result = 125
                    continue
                for owner in root.rglob('*.owner.json'):
                    pidfile = str(owner.resolve())[:-len('.owner.json')]
                    if pidfile in seen:
                        continue
                    seen.add(pidfile)
                    record = read_owner(pidfile)
                    if not record:
                        result = 125
                        continue
                    output, code = cancel(pidfile, record['task'])
                    print(json.dumps(output, ensure_ascii=False, separators=(',', ':')))
                    if code:
                        result = code
        old_files = []
        for root in roots:
            if root.is_dir():
                if not root.resolve().is_relative_to(module):
                    continue
                for pattern in ('*worker.pid', 'font-prewarm-*.pid', '*provider*.pid'):
                    old_files.extend(root.glob(pattern))
        old_files.append(module / '.google-font-provider.lock/pid')
        for pidfile in old_files:
            if pidfile.exists() and str(pidfile.resolve()) not in seen and not Path(str(pidfile) + '.owner.json').exists():
                code = legacy_cancel(pidfile, module)
                if code:
                    result = code
        return result
    if args.action == 'run':
        if args.command[:1] == ['--']:
            args.command.pop(0)
        if not args.command:
            return 2
        return run(args)
    if args.action == 'alive':
        record = read_owner(args.pidfile)
        return 0 if same_process(record) and (not args.task or record['task'] == args.task) else 1
    if args.action == 'cleaned':
        return 0 if cleaned(args.pidfile, args.task) else 1
    if args.action == 'settled':
        return settled(args.pidfile)
    result, code = cancel(args.pidfile, args.task)
    print(json.dumps(result, ensure_ascii=False, separators=(',', ':')))
    return code


if __name__ == '__main__':
    sys.exit(main())
