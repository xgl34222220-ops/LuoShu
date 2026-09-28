#!/usr/bin/env python3
"""One-shot Linux/Android task ownership, deadlines and descendant reaping.

PR_SET_CHILD_SUBREAPER retains ownership of orphan/double-fork children. Only
current descendants whose /proc start-time still matches are signalled. This
process exists only while a requested task or its bounded cleanup is running.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def identity(pid: int) -> tuple[int, int, str] | None:
    try:
        tail = Path(f'/proc/{pid}/stat').read_text().rsplit(') ', 1)[1].split()
        return int(tail[1]), int(tail[19]), tail[0]  # ppid, starttime, state
    except (OSError, ValueError, IndexError):
        return None


def descendants() -> dict[int, tuple[int, int, str]]:
    records = {}
    with os.scandir('/proc') as entries:
        for entry in entries:
            if entry.name.isdigit():
                pid = int(entry.name)
                record = identity(pid)
                if record is not None:
                    records[pid] = record
    owned = {os.getpid()}
    changed = True
    while changed:
        changed = False
        for pid, record in records.items():
            if pid not in owned and record[0] in owned:
                owned.add(pid)
                changed = True
    return {pid: records[pid] for pid in owned if pid != os.getpid()}


def signal_owned(records: dict, sig: int) -> int:
    sent = 0
    # Identity is checked again immediately before signalling, so unrelated
    # processes which reuse an exited child's PID are not targeted.
    for pid, old in records.items():
        now = identity(pid)
        if now is None or now[1] != old[1] or now[2] == 'Z':
            continue
        try:
            os.kill(pid, sig)
            sent += 1
        except ProcessLookupError:
            pass
    return sent


def reap(proc: subprocess.Popen) -> int:
    count = 0
    while True:
        try:
            pid, status = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            break
        if pid == 0:
            break
        if pid == proc.pid:
            proc.returncode = os.waitstatus_to_exitcode(status)
        count += 1
    return count


def cleanup(proc: subprocess.Popen) -> tuple[int, int, list[int]]:
    terminated = reaped = 0
    started = time.monotonic()
    deadline = started + 3.0
    # Signal the initial worker tree once, then allow EXIT traps to launch
    # their short cleanup utilities. Re-signalling every newly spawned `rm`,
    # `awk` or `sleep` used to abort those traps and leave a live-lease lock.
    # Only the grace period changes; the total cleanup deadline stays bounded.
    graceful_until = started + (2.0 if proc.poll() is None else 0.6)
    initial = descendants()
    terminated += signal_owned(initial, signal.SIGTERM)
    while True:
        reaped += reap(proc)
        children = descendants()
        if not children:
            return terminated, reaped, []
        now = time.monotonic()
        if now >= deadline:
            return terminated, reaped, sorted(children)
        if now >= graceful_until:
            terminated += signal_owned(children, signal.SIGKILL)
        time.sleep(0.04)


def release_pid(pid_file: str, task: str, report: dict) -> None:
    if not pid_file:
        return
    path = Path(pid_file)
    try:
        if path.read_text().strip() != str(os.getpid()):
            return
        if Path(pid_file + '.task').read_text().strip() != task:
            return
        proof = Path(pid_file + '.cleanup.json')
        temp = proof.with_name(proof.name + f'.tmp.{os.getpid()}')
        temp.write_text(json.dumps(report, ensure_ascii=False) + '\n')
        os.chmod(temp, 0o600)
        os.replace(temp, proof)
        if report['leftoverPids']:
            return  # Keep evidence; do not pretend an unkillable child exited.
        for suffix in ('', '.task', '.boot'):
            Path(pid_file + suffix).unlink(missing_ok=True)
    except OSError as error:
        print(f'洛书：无法保存任务退出记录：{error}', file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid-file', default='')
    parser.add_argument('--task', default='')
    parser.add_argument('--timeout', type=float, default=360.0)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command
    if command[:1] == ['--']:
        command = command[1:]
    if not command or not 0.1 <= args.timeout <= 900:
        parser.error('a command and a timeout in [0.1, 900] seconds are required')
    interrupted = 0

    def on_signal(sig: int, _frame: object) -> None:
        nonlocal interrupted
        interrupted = interrupted or sig

    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, on_signal)
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
            raise OSError(ctypes.get_errno(), 'PR_SET_CHILD_SUBREAPER')
    except (AttributeError, OSError) as error:
        print(f'洛书：无法建立任务子进程回收范围，未启动任务：{error}', file=sys.stderr)
        return 126

    # The launcher writes identity sidecars immediately after forking us. Wait
    # before starting a fast command so completion cannot race its PID write.
    if args.pid_file:
        ready_deadline = time.monotonic() + 2
        while True:
            try:
                ready = (Path(args.pid_file).read_text().strip() == str(os.getpid())
                         and Path(args.pid_file + '.task').read_text().strip() == args.task
                         and Path(args.pid_file + '.boot').read_text().strip()
                         == Path('/proc/sys/kernel/random/boot_id').read_text().strip())
            except OSError:
                ready = False
            if ready:
                break
            if interrupted or time.monotonic() >= ready_deadline:
                return 128 + interrupted if interrupted else 126
            time.sleep(0.02)
    env = dict(os.environ)
    env['LUOSHU_TASK_SCOPE_PID'] = str(os.getpid())
    env['LUOSHU_TASK_SCOPE_PID_FILE'] = args.pid_file
    env['LUOSHU_TASK_SCOPE_TASK'] = args.task
    started = time.monotonic()
    proc = None
    result = 126
    timed_out = False
    terminated = reaped = 0
    leftovers: list[int] = []
    try:
        proc = subprocess.Popen(
            ['sh', '-c', 'LUOSHU_SCOPE_WORKER_PID=$$; export LUOSHU_SCOPE_WORKER_PID; exec "$@"',
             'luoshu-task', *command], env=env, start_new_session=True)
        while proc.poll() is None:
            if interrupted:
                result = 128 + interrupted
                break
            if time.monotonic() - started >= args.timeout:
                timed_out = True
                result = 124
                break
            time.sleep(0.1)
        else:
            result = proc.returncode
            if result < 0:
                result = 128 - result
    except (OSError, ValueError) as error:
        print(f'洛书：无法执行字体任务：{error}', file=sys.stderr)
    finally:
        if proc is not None:
            terminated, reaped, leftovers = cleanup(proc)
        if interrupted:
            result = 128 + interrupted
        if leftovers:
            result = 125
        report = {'schema': 'luoshu-task-cleanup-v1', 'task': args.task,
                  'result': result, 'deadlineExceeded': timed_out,
                  'terminationSignal': interrupted, 'terminated': terminated,
                  'reaped': reaped, 'leftoverPids': leftovers,
                  'durationSeconds': round(time.monotonic() - started, 3)}
        release_pid(args.pid_file, args.task, report)
        print('[TASK-CLEANUP] ' + json.dumps(report, ensure_ascii=False), file=sys.stderr)
    return result


if __name__ == '__main__':
    raise SystemExit(main())
