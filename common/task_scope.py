#!/usr/bin/env python3
"""Finite LuoShu task supervisor; never changes a mount/PID namespace.

PR_SET_CHILD_SUBREAPER keeps double-forked/setsid workers adoptable. Signals are
sent only to proven descendants or to the exact random, inherited scope token,
and always to the recorded boot + process start time (pidfds where supported).
There is no idle daemon: the supervisor exits after its one worker is reaped.
"""
import argparse
import ctypes
import errno
import fcntl
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import time
import uuid

PROC = Path('/proc')
SUFFIXES = ('', '.task', '.boot', '.start', '.scope', '.identity', '.cancel')
LIBC = ctypes.CDLL(None, use_errno=True)
LIBC.syscall.restype = ctypes.c_long


def read(path):
    try:
        return Path(path).read_text().strip()
    except (OSError, UnicodeError):
        return ''


def boot_id():
    return read(PROC / 'sys/kernel/random/boot_id')


def proc_info(pid):
    try:
        # comm may contain spaces and parentheses; use the final closing paren.
        tail = (PROC / str(pid) / 'stat').read_text().rsplit(') ', 1)[1].split()
        return {'pid': int(pid), 'ppid': int(tail[1]), 'start': int(tail[19]),
                'state': tail[0]}
    except (OSError, ValueError, IndexError):
        return None


def same_process(record, include_zombie=False):
    now = proc_info(record['pid'])
    return bool(now and now['start'] == record['start'] and
                (include_zombie or now['state'] not in ('Z', 'X')))


def pidfd_open(pid):
    if hasattr(os, 'pidfd_open'):
        return os.pidfd_open(pid)
    # Android's CPython build may omit the wrapper although its kernel supports
    # pidfds. These are Linux generic syscall numbers on the shipped ARM64 ABI
    # and on the x86_64 Android validation target, not architecture guesses.
    if os.uname().machine not in ('aarch64', 'arm64', 'x86_64'):
        raise OSError(errno.ENOSYS, 'Unsupported pidfd syscall ABI')
    fd = LIBC.syscall(ctypes.c_long(434), ctypes.c_int(pid), ctypes.c_uint(0))
    if fd < 0:
        raise OSError(ctypes.get_errno(), 'pidfd_open')
    return int(fd)


def pidfd_send(fd, sig):
    if hasattr(signal, 'pidfd_send_signal'):
        return signal.pidfd_send_signal(fd, sig)
    if os.uname().machine not in ('aarch64', 'arm64', 'x86_64'):
        raise OSError(errno.ENOSYS, 'Unsupported pidfd syscall ABI')
    result = LIBC.syscall(ctypes.c_long(424), ctypes.c_int(fd), ctypes.c_int(sig),
                          ctypes.c_void_p(), ctypes.c_uint(0))
    if result < 0:
        raise OSError(ctypes.get_errno(), 'pidfd_send_signal')


def unreaped_child(record):
    """A direct child cannot have its PID recycled until THIS process reaps it.

    This process is single-threaded and this function never waits/reaps. Linux
    waitid(WNOWAIT) proves parenthood; a /proc PPID comparison alone would race.
    """
    if not hasattr(os, 'waitid') or not hasattr(os, 'WNOWAIT'):
        return False
    try:
        child = os.waitid(os.P_PID, record['pid'], os.WEXITED | os.WNOHANG | os.WNOWAIT)
        return child is None and same_process(record)
    except (OSError, ChildProcessError):
        return False


def signal_process(record, sig):
    """Pin identity with pidfd, or with unreaped direct-child ownership.

    There is deliberately NO read-starttime-then-kill fallback for arbitrary
    PIDs. On older kernels, cleanup kills/adopts one descendant generation at
    a time. Recovery of a killed supervisor fails closed without pidfds.
    """
    if record['pid'] <= 1 or record['pid'] == os.getpid():
        return False
    fd = None
    try:
        try:
            fd = pidfd_open(record['pid'])
        except OSError as exc:
            if exc.errno not in (errno.ENOSYS, errno.EINVAL, errno.EPERM):
                return False
        if not same_process(record):
            return False
        if fd is not None:
            pidfd_send(fd, sig)
        elif unreaped_child(record):
            os.kill(record['pid'], sig)
        else:
            return False
        return True
    except (OSError, ValueError):
        return False
    finally:
        if fd is not None:
            os.close(fd)


def snapshot():
    found = {}
    for item in PROC.iterdir():
        if item.name.isdigit():
            info = proc_info(int(item.name))
            if info:
                found[info['pid']] = info
    return found


def descendants(root, processes):
    owned = {root}
    changed = True
    while changed:
        changed = False
        for pid, info in processes.items():
            if info['ppid'] in owned and pid not in owned:
                owned.add(pid)
                changed = True
    return [processes[pid] for pid in owned if pid != root and pid in processes]


def token_members(token, minimum_start, processes):
    marker = ('LUOSHU_TASK_SCOPE=' + token).encode()
    result = []
    for pid, info in processes.items():
        if info['start'] < minimum_start or pid <= 1 or pid == os.getpid():
            continue
        try:
            if marker in (PROC / str(pid) / 'environ').read_bytes().split(b'\0'):
                result.append(info)
        except OSError:
            pass
    return result


def atomic_write(path, text):
    path = Path(path)
    tmp = path.with_name(path.name + '.tmp.' + str(os.getpid()))
    tmp.write_text(text)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def load_identity(pidfile):
    try:
        data = json.loads(read(str(pidfile) + '.identity'))
        # Previous-boot identities still prove ownership of their temporary
        # files. They must survive loading so recovery can remove those files;
        # process authority is checked separately against the current boot.
        if (not isinstance(data['boot'], str) or not data['boot'] or
                not isinstance(data['token'], str) or len(data['token']) != 32):
            return None
        int(data['owner']['pid']); int(data['owner']['start'])
        return data
    except (ValueError, KeyError, TypeError):
        return None


def identity_alive(data):
    return bool(data and data.get('boot') == boot_id() and same_process(data['owner']))


def clear_identity(pidfile, token):
    # Publication/replacement is serialized by launch's flock. Match the token
    # again so an older task can never clear a newer task's sidecars.
    if read(str(pidfile) + '.scope') != token:
        return
    for suffix in SUFFIXES:
        try:
            Path(str(pidfile) + suffix).unlink()
        except FileNotFoundError:
            pass


def state_values(path):
    return dict(line.split('=', 1) for line in read(path).splitlines() if '=' in line)


def task_state_path(pidfile):
    name = Path(pidfile).name
    if name == 'switch_task_worker.pid':
        return Path(os.environ.get('LUOSHU_SWITCH_TASK_FILE', str(Path(pidfile).parent / 'switch_task.conf')))
    if name in ('axes_worker.pid', 'auto_multiweight_worker.pid'):
        return Path(pidfile).parent / 'axes_task.conf'
    if name == 'mix_worker.pid':
        return Path(pidfile).parent / 'mix_task.conf'
    return None


def mark_failed(pidfile, task, message, include_success=False):
    path = task_state_path(pidfile)
    if not path:
        return
    values = state_values(path)
    eligible = ('queued', 'running', 'success') if include_success else ('queued', 'running')
    if values.get('task') != task or values.get('state') not in eligible:
        return
    values.update(state='failed', message=message, percent='100',
                  finished=str(int(time.time())), pid='')
    # Exact task ownership checked again immediately before atomic replacement.
    if state_values(path).get('task') == task:
        atomic_write(path, ''.join(f'{key}={value}\n' for key, value in values.items()))


def claim_workspace(pidfile, task, token):
    module = Path(pidfile).resolve().parent.parent
    workspace = module / 'cache' / 'tasks' / token
    workspace.mkdir(mode=0o700, parents=True, exist_ok=False)
    atomic_write(workspace / '.luoshu-task-owner', token)
    owned = [str(workspace)]
    state = task_state_path(pidfile)
    values = state_values(state) if state else {}
    root = Path(values.get('root', '/'))
    # Old controllers make their request directory before starting the worker.
    # Claim only that exact current task directory, never a shared cache/stage.
    if (values.get('task') == task and root.name == task and
            root.parent.name in ('axes-mix', 'auto-multiweight-mix') and
            root.parent.parent.resolve() == (module / 'cache').resolve() and
            root.is_dir() and not root.is_symlink()):
        marker = root / '.luoshu-task-owner'
        if not marker.exists():
            atomic_write(marker, token)
            owned.append(str(root))
    return workspace, owned


def clear_workspaces(data):
    for raw in data.get('workspaces', []):
        path = Path(raw)
        # An exact marker is required even after cancellation/recovery; never
        # infer ownership from an attractive-looking directory name alone.
        if not path.is_symlink() and read(path / '.luoshu-task-owner') == data['token']:
            shutil.rmtree(path, ignore_errors=True)


class Scope:
    def __init__(self, pidfile, task, token):
        self.pidfile = pidfile
        self.task = task
        self.token = token
        self.owner = proc_info(os.getpid())
        self.members = {}
        self.last_saved = 0.0
        self.data = {'version': 1, 'task': task, 'token': token, 'boot': boot_id(),
                     'owner': self.owner, 'members': []}

    def discover(self, inherited=False):
        processes = snapshot()
        found = descendants(os.getpid(), processes)
        if inherited:
            found += token_members(self.token, self.owner['start'], processes)
        for member in found:
            self.members[(member['pid'], member['start'])] = member
        self.members = {key: value for key, value in self.members.items()
                        if same_process(value, include_zombie=True)}
        return list(self.members.values())

    def save(self, force=False):
        now = time.monotonic()
        if force or now - self.last_saved >= 0.5:
            self.data['members'] = list(self.members.values())
            atomic_write(str(self.pidfile) + '.identity', json.dumps(self.data))
            self.last_saved = now

    def publish(self):
        if not self.owner or not self.data['boot']:
            raise RuntimeError('Cannot verify task boot/process identity')
        self.save(True)
        for suffix, value in (('.task', self.task), ('.boot', self.data['boot']),
                              ('.start', self.owner['start']), ('.scope', self.token),
                              ('', self.owner['pid'])):
            atomic_write(str(self.pidfile) + suffix, str(value) + '\n')

    def cleanup(self, reap):
        # TERM descendants together, then reap/adopt repeatedly. New children
        # made by a TERM trap are discovered on the next pass, not forgotten.
        for sig, duration in ((signal.SIGTERM, 1.5), (signal.SIGKILL, 3.0)):
            end = time.monotonic() + duration
            while True:
                members = self.discover(inherited=True)
                for member in members:
                    signal_process(member, sig)
                reap()
                if not self.discover(inherited=True):
                    return True
                self.save()
                if time.monotonic() >= end:
                    break
                time.sleep(0.05)
        return False


def subreaper():
    if LIBC.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
        raise OSError(ctypes.get_errno(), 'Cannot create bounded child-reaper scope')


def timeout_value():
    try:
        return max(1.0, min(3600.0, float(os.environ.get('LUOSHU_TASK_TIMEOUT_SECONDS', '900'))))
    except ValueError:
        return 900.0


def supervise(args):
    scope = Scope(args.pidfile, args.task, args.token)
    caught = []
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, lambda number, _frame: caught.append(number))
    worker_pid = None
    worker_status = None

    def reap():
        nonlocal worker_status
        while True:
            try:
                pid, status = os.waitpid(-1, os.WNOHANG)
            except ChildProcessError:
                break
            if not pid:
                break
            if pid == worker_pid:
                worker_status = os.waitstatus_to_exitcode(status)

    last_discovery = 0.0

    def tick():
        nonlocal last_discovery
        if read(str(args.pidfile) + '.cancel') == args.token and not caught:
            caught.append(signal.SIGTERM)
        now = time.monotonic()
        # The kernel adopts orphans without polling. Snapshot at most once per
        # second during work, just to persist crash-recovery evidence. Cleanup
        # is the only phase that needs repeated dense process discovery.
        if now - last_discovery >= 1.0:
            scope.discover()
            scope.save()
            last_discovery = now
        reap()

    try:
        subreaper()
        workspace, owned = claim_workspace(args.pidfile, args.task, args.token)
        scope.data['workspaces'] = owned
        scope.publish()
        env = dict(os.environ, LUOSHU_TASK_SCOPE=args.token,
                   LUOSHU_TASK_OWNER_PID=str(os.getpid()),
                   LUOSHU_TASK_OWNER_START=str(scope.owner['start']),
                   LUOSHU_TASK_PID_FILE=str(args.pidfile),
                   LUOSHU_TASK_WORK_DIR=str(workspace), TMPDIR=str(workspace))
        worker = subprocess.Popen(args.command, env=env, close_fds=True)
        worker_pid = worker.pid
        # waitpid above owns ALL child reaping, including Popen's initial child.
        os.write(args.ready_fd, b'OK\n')
        os.close(args.ready_fd)
        args.ready_fd = -1
        deadline = time.monotonic() + timeout_value()
        while worker_status is None and not caught and time.monotonic() < deadline:
            tick()
            time.sleep(0.2)
        if caught:
            result = 128 + caught[0]
            mark_failed(args.pidfile, args.task, '字体任务已取消，后台进程已回收')
        elif worker_status is None:
            result = 124
            mark_failed(args.pidfile, args.task, '字体任务执行超时，后台进程已回收')
        else:
            result = worker_status if worker_status >= 0 else 128 - worker_status
            mark_failed(args.pidfile, args.task, '字体任务进程已结束，请重新应用')
            # The frozen v14 fixed-weight engine announces generation success
            # before its existing monitor commits the next-boot payload. Let
            # ONLY that bounded completion finish before cleaning the scope.
            request = os.environ.get('LUOSHU_MIX_REQUEST_ID', '')
            state_path = task_state_path(args.pidfile)
            values = state_values(state_path) if state_path else {}
            if (result == 0 and request and values.get('task') == args.task and
                    values.get('state') == 'success' and values.get('childTask')):
                final_path = Path(args.pidfile).parent / 'mix-finalize-state.conf'
                # Commit shares the original whole-task deadline. Do not add
                # an arbitrary shorter window for large fonts on slower CPUs.
                finish_deadline = deadline
                committed = False
                while not caught and time.monotonic() < finish_deadline:
                    final = state_values(final_path)
                    if final.get('requestId') == request:
                        if final.get('state') == 'success':
                            committed = True
                            break
                        if final.get('state') == 'failed':
                            break
                    tick()
                    time.sleep(0.1)
                if not committed:
                    result = 124 if not caught else 128 + caught[0]
                    mark_failed(args.pidfile, args.task,
                                '复合字体下一启动负载未完成提交，请重新应用', True)
        cleaned = scope.cleanup(reap)
        if cleaned:
            clear_workspaces(scope.data)
            clear_identity(args.pidfile, args.token)
        else:
            # Uninterruptible I/O can delay SIGKILL. Keep exact identities for
            # recovery rather than claiming cleanup or starting another task.
            scope.save(True)
            mark_failed(args.pidfile, args.task, '后台任务仍在等待内核 I/O，请稍后重试', True)
            result = 125
        worker.returncode = worker_status if worker_status is not None else -signal.SIGKILL
        return result
    except BaseException as exc:
        print(f'[task-scope] {type(exc).__name__}: {exc}', file=sys.stderr)
        cleaned = not worker_pid or scope.cleanup(reap)
        if cleaned:
            clear_workspaces(scope.data)
            clear_identity(args.pidfile, args.token)
        else:
            scope.save(True)
        return 125
    finally:
        if args.ready_fd >= 0:
            os.close(args.ready_fd)


def recover(data):
    """Recovery after a dead supervisor; old/reused owner PIDs are NOT targets."""
    if not data or data['boot'] != boot_id():
        return True
    records = {(v['pid'], v['start']): v for v in data.get('members', [])}
    for sig, duration in ((signal.SIGTERM, 1.5), (signal.SIGKILL, 3.0)):
        end = time.monotonic() + duration
        while True:
            for info in token_members(data['token'], data['owner']['start'], snapshot()):
                records[(info['pid'], info['start'])] = info
            records = {key: value for key, value in records.items() if same_process(value)}
            if not records:
                return True
            for record in records.values():
                signal_process(record, sig)
            if time.monotonic() >= end:
                break
            time.sleep(0.05)
    return not any(same_process(value) for value in records.values())


def launch(args):
    pidfile = Path(args.pidfile).absolute()
    pidfile.parent.mkdir(parents=True, exist_ok=True)
    Path(args.log).parent.mkdir(parents=True, exist_ok=True)
    with open(str(pidfile) + '.launch-lock', 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        data = load_identity(pidfile)
        if identity_alive(data):
            return 3
        if data:
            if not recover(data):
                return 4
            clear_workspaces(data)
        token = uuid.uuid4().hex
        read_fd, write_fd = os.pipe()
        os.set_inheritable(write_fd, True)
        command = [sys.executable, str(Path(__file__).resolve()), 'supervise',
                   str(pidfile), args.task, token, str(write_fd), '--', *args.command]
        with open(os.devnull, 'rb') as null, open(args.log, 'ab', buffering=0) as log:
            process = subprocess.Popen(command, stdin=null, stdout=log, stderr=log,
                                       start_new_session=True, pass_fds=(write_fd,))
        os.close(write_fd)
        # Only the finite supervisor owns the write end; a failed import/prctl
        # closes it immediately. Bound this handshake even on a broken runtime.
        import select
        ready = select.select([read_fd], [], [], 10)[0]
        reply = os.read(read_fd, 16) if ready else b''
        os.close(read_fd)
        if reply != b'OK\n':
            record = proc_info(process.pid)
            if record:
                signal_process(record, signal.SIGTERM)
            return 1
        return 0


def stop(args):
    data = load_identity(args.pidfile)
    if not data or (args.task and data['task'] != args.task):
        return 0
    if identity_alive(data):
        # Cancellation is a scoped request, not an external numeric-PID kill.
        # This remains safe on kernels without pidfds.
        if read(str(args.pidfile) + '.scope') != data['token']:
            return 0
        atomic_write(str(args.pidfile) + '.cancel', data['token'] + '\n')
        deadline = time.monotonic() + 8
        while identity_alive(data) and time.monotonic() < deadline:
            time.sleep(0.05)
        # Never kill a still-running reaper. It is the process that owns its
        # children's waitpid lifecycle, and may be finishing rollback.
        if identity_alive(data):
            return 1
    if recover(data):
        clear_workspaces(data)
        clear_identity(args.pidfile, data['token'])
        return 0
    return 1


def terminate_tree(args):
    root = proc_info(args.pid)
    if (not args.start or not root or root['pid'] <= 1 or root['pid'] == os.getpid() or
            str(root['start']) != args.start):
        return 1
    records = {(root['pid'], root['start']): root}
    this_boot = boot_id()
    for sig, duration in ((signal.SIGTERM, 1.5), (signal.SIGKILL, 3.0)):
        deadline = time.monotonic() + duration
        while this_boot and boot_id() == this_boot:
            if same_process(root):
                for item in descendants(root['pid'], snapshot()):
                    records[(item['pid'], item['start'])] = item
            live = [item for item in records.values() if same_process(item)]
            if not live:
                return 0
            # Every arbitrary external PID is pinned by pidfd. Without kernel
            # support, do not pretend birth-time polling closes the signal race.
            for item in reversed(live):
                signal_process(item, sig)
            if time.monotonic() >= deadline:
                break
            time.sleep(.05)
    return 1


def reconcile(args):
    data = load_identity(args.pidfile)
    if not data or identity_alive(data):
        return 0
    if not recover(data):
        return 1
    mark_failed(args.pidfile, data['task'], '字体任务进程已结束，后台工作已回收')
    clear_workspaces(data)
    clear_identity(args.pidfile, data['token'])
    return 0


def submit(args):
    """Serialize the *request*, before frozen mix_router creates any stage."""
    config = Path(args.config)
    config.mkdir(parents=True, exist_ok=True)
    with open(config / '.mix-submit-lock', 'a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('{"status":"error","message":"已有字体组合任务正在启动"}')
            return 0
        for name in ('axes_worker.pid', 'auto_multiweight_worker.pid', 'mix_worker.pid'):
            pidfile = config / name
            data = load_identity(pidfile)
            if identity_alive(data):
                print('{"status":"error","message":"已有字体组合任务正在运行"}')
                return 0
            if data:
                if not recover(data):
                    print('{"status":"error","message":"上一字体任务仍在回收，请稍后重试"}')
                    return 0
                clear_workspaces(data)
                clear_identity(pidfile, data['token'])
        return subprocess.call(args.command)


def lock_fd(args):
    """Lock the caller's inherited open-file description, not a PID file.

    The shell keeps its copy of this descriptor open across the critical
    section. Exiting this short helper does not release the shared flock.
    Never unlink the backing file: existing waiters must keep the same inode.
    """
    if args.fd < 3 or not 0 <= args.timeout <= 3600:
        return 2
    deadline = time.monotonic() + args.timeout
    while True:
        try:
            fcntl.flock(args.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return 0
        except BlockingIOError:
            if time.monotonic() >= deadline:
                return 1
            time.sleep(.05)
        except OSError:
            return 1


def error_message_from_file(path):
    """Read a bounded manager-output tail without Android libc regex calls.

    Managers emit standalone JSON records amongst human-readable log lines.
    Preserve the last valid top-level string message, never a nested lookalike
    or a malformed JSON fragment. The persisted task format is one key per line.
    """
    limit = 256 * 1024
    try:
        if not Path(path).is_file():
            return ''
        with open(path, 'rb') as source:
            source.seek(0, os.SEEK_END)
            offset = max(0, source.tell() - limit)
            source.seek(offset)
            raw = source.read(limit)
        if offset:
            # The first bytes may be the middle of a log/UTF-8/JSON record.
            # Do not reinterpret a cut-off record as an independent response.
            raw = raw.partition(b'\n')[2]
        text = raw.decode('utf-8', errors='replace')
    except OSError:
        return ''

    def extract(candidate):
        if not candidate.lstrip().startswith('{'):
            return ''
        try:
            value = json.loads(candidate)
        except (ValueError, RecursionError):
            return ''
        message = value.get('message') if isinstance(value, dict) else None
        if not isinstance(message, str):
            return ''
        # JSON escapes can include newlines, NULs or lone surrogates. Decode
        # correctly, then prevent them from injecting additional task fields.
        message = ''.join(' ' if ord(char) < 32 or char in '\x7f\x85\u2028\u2029' else char
                          for char in message[:4096]).strip()
        return message.encode('utf-8', errors='replace').decode('utf-8')

    # A complete pretty-printed response is valid too. Otherwise parse separate
    # log records in reverse; total examined input remains bounded above.
    complete = extract(text)
    if complete:
        return complete
    try:
        json.loads(text)
    except (ValueError, RecursionError):
        pass
    else:
        # A valid whole response without a top-level string message must not
        # accidentally expose a nested object while scanning individual lines.
        return ''
    for line in reversed(text.splitlines()):
        message = extract(line)
        if message:
            return message
    return ''


def error_message(args):
    message = error_message_from_file(args.path)
    if not message:
        return 1
    print(message)
    return 0


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest='action', required=True)
    start = commands.add_parser('launch')
    start.add_argument('pidfile'); start.add_argument('task'); start.add_argument('log')
    start.add_argument('command', nargs=argparse.REMAINDER)
    run = commands.add_parser('supervise')
    run.add_argument('pidfile'); run.add_argument('task'); run.add_argument('token')
    run.add_argument('ready_fd', type=int); run.add_argument('command', nargs=argparse.REMAINDER)
    end = commands.add_parser('stop')
    end.add_argument('pidfile'); end.add_argument('task', nargs='?', default='')
    tree = commands.add_parser('tree')
    tree.add_argument('pid', type=int); tree.add_argument('start', nargs='?', default='')
    repair = commands.add_parser('reconcile')
    repair.add_argument('pidfile')
    admission = commands.add_parser('submit')
    admission.add_argument('config'); admission.add_argument('command', nargs=argparse.REMAINDER)
    mutex = commands.add_parser('lock-fd')
    mutex.add_argument('fd', type=int); mutex.add_argument('timeout', type=float)
    message = commands.add_parser('error-message')
    message.add_argument('path')
    args = parser.parse_args()
    if hasattr(args, 'command'):
        if args.command[:1] == ['--']:
            args.command.pop(0)
        if not args.command:
            parser.error('missing task command')
    return {'launch': launch, 'supervise': supervise, 'stop': stop, 'reconcile': reconcile,
            'submit': submit, 'tree': terminate_tree, 'lock-fd': lock_fd,
            'error-message': error_message}[args.action](args)


if __name__ == '__main__':
    sys.exit(main())
