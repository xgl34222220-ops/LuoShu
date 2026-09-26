#!/usr/bin/env python3
"""Supervise one mapper using real work progress and descendant CPU activity."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def values(path: Path) -> dict[str, str]:
    try:
        return dict(line.split('=', 1) for line in path.read_text().splitlines() if '=' in line)
    except OSError:
        return {}


def cpu_snapshot(root: int, proc_root: Path = Path('/proc')) -> tuple:
    """No ps polling or FontTools loading. Only this worker's descendant tree."""
    pending, seen, records, missing_children = [root], set(), [], False
    while pending:
        pid = pending.pop()
        if pid in seen:
            continue
        seen.add(pid)
        try:
            # comm may contain spaces or parentheses; fields after the last ') '
            # start at state (field 3), utime/stime are offsets 11 and 12.
            tail = (proc_root / str(pid) / 'stat').read_text().rsplit(') ', 1)[1].split()
            records.append((pid, tail[19], sum(map(int, tail[11:15]))))
            try:
                pending.extend(map(int, (proc_root / str(pid) / 'task' / str(pid) / 'children').read_text().split()))
            except OSError:
                missing_children = True
        except (OSError, ValueError, IndexError):
            continue
    if missing_children:
        # Older kernels can omit task/children. Read ppid from stat instead of
        # treating a sleeping shell as an idle FontTools descendant.
        parents, stats = {}, {}
        for path in proc_root.glob('[0-9]*/stat'):
            try:
                pid = int(path.parent.name)
                tail = path.read_text().rsplit(') ', 1)[1].split()
                parents.setdefault(int(tail[1]), []).append(pid)
                stats[pid] = (pid, tail[19], sum(map(int, tail[11:15])))
            except (OSError, ValueError, IndexError):
                continue
        pending, seen, records = [root], set(), []
        while pending:
            pid = pending.pop()
            if pid in seen:
                continue
            seen.add(pid)
            if pid in stats:
                records.append(stats[pid])
            pending.extend(parents.get(pid, []))
    return tuple(sorted(records))


def stop_group(process: subprocess.Popen) -> None:
    # Killing only the shell leaves an orphan Python worker writing into the
    # stage after its lock has been released. The whole owned session must stop.
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(process.pid, sig)
        except ProcessLookupError:
            break
        if sig == signal.SIGTERM:
            time.sleep(0.25)
    try:
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass


def progress(path: Path) -> dict:
    try:
        result = json.loads(path.read_text())
        completed, total = int(result['completed']), int(result['total'])
        if 0 <= completed <= total and total > 0:
            return {**result, 'completed': completed, 'total': total}
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return {}


def publish(module: Path, request: str, task: str, work: dict, elapsed: int) -> None:
    if values(module / 'config/mix-stage-next.conf').get('requestId') != request:
        return
    current_task = values(module / 'config/axes_task.conf').get('task')
    if current_task and current_task != task:
        return
    names = {'selection': '核对原厂字形', 'supplement': '组合字体', 'metrics': '匹配系统度量',
             'complete': '核验生成结果', 'stock': '核对原厂字形', 'prepare': '准备字体',
             'source': '读取选中字体', 'inventory': '核对扫描清单'}
    phase = names.get(str(work.get('phase', '')), str(work.get('phase') or '准备本机字体清单'))
    done, total = work.get('completed', 0), work.get('total', 0)
    message = f'{phase}：{done}/{total}，已用 {elapsed} 秒' if total else f'{phase}，已用 {elapsed} 秒'
    if work.get('path'):
        message += ' · ' + Path(str(work['path'])).name
    # No elapsed-time estimate pretending to be completion percentage.
    percent = 70 + (27 * done // total if total else 0)
    fields = {'state': 'running', 'task': task, 'requestId': request, 'message': message,
              'percent': str(percent), 'elapsed': str(elapsed), 'completed': str(done),
              'total': str(total), 'time': str(int(time.time()))}
    output = module / 'config/mix-finalize-state.conf'
    temporary = output.with_name(output.name + f'.tmp.{os.getpid()}')
    temporary.write_text(''.join(f'{key}={str(value).replace(chr(10), " ").replace(chr(13), " ")}\n'
                                 for key, value in fields.items()))
    os.replace(temporary, output)


def supervise(module: Path, request: str, task: str, progress_file: Path, command: list[str],
              idle_seconds: float = 120, max_seconds: float = 600, poll_seconds: float = .5) -> int:
    progress_file.unlink(missing_ok=True)
    env = dict(os.environ, LUOSHU_INVENTORY_PROGRESS_FILE=str(progress_file))
    process = subprocess.Popen(command, env=env, start_new_session=True)
    start = last_work = time.monotonic()
    last_cpu, last_progress = (), None
    interrupted = []
    def interrupted_handler(signum, _frame):
        interrupted.append(signum)
    old_handlers = {sig: signal.signal(sig, interrupted_handler)
                    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)}
    try:
        while process.poll() is None:
            now = time.monotonic()
            work = progress(progress_file)
            token = (work.get('completed'), work.get('total'), work.get('phase'), work.get('path'))
            cpu = cpu_snapshot(process.pid)
            if token != last_progress or cpu != last_cpu:
                last_work, last_progress, last_cpu = now, token, cpu
            publish(module, request, task, work, int(now - start))
            reason, result = '', 124
            if interrupted:
                reason, result = '本次字体生成已取消，已停止全部子进程', 128 + interrupted[0]
            elif values(module / 'config/mix-stage-next.conf').get('requestId') != request:
                reason, result = '字体任务已被新请求替换，已停止旧任务', 125
            elif now - start >= max_seconds:
                reason = f'本机字体生成已达 {max_seconds:g} 秒总时限，已停止全部子进程'
            elif now - last_work >= idle_seconds:
                reason = f'本机字体生成连续 {idle_seconds:g} 秒无处理进展，已停止全部子进程'
            if reason:
                stop_group(process)
                print('通用字体生成失败：' + reason, file=sys.stderr, flush=True)
                return result
            time.sleep(poll_seconds)
        return process.returncode
    finally:
        if process.poll() is None:
            stop_group(process)
        for sig, handler in old_handlers.items():
            signal.signal(sig, handler)


def locked_run(module: Path, command: list[str], wait_seconds: float) -> int:
    """A persistent inode and inherited FD prevent mkdir-reclamation ABA.

    FD 9 stays with the transaction shell even if this Python parent is killed.
    The router explicitly closes FD 9 in its start/daemon-launch child, so a
    detached controller cannot retain the admission lock or deadlock finalize.
    Never unlink the file or explicitly unlock: the last descriptor releases it.
    """
    import fcntl
    lock = module / '.mix-stage-finalize.flock'
    descriptor = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
    interrupted = []
    old_handlers = {sig: signal.signal(sig, lambda signum, frame: interrupted.append(signum))
                    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)}
    process = None
    inherited = False
    try:
        deadline = time.monotonic() + wait_seconds
        while True:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if interrupted:
                    return 128 + interrupted[0]
                if time.monotonic() >= deadline:
                    print('{"status":"error","message":"字体组合正在提交，请稍后重试"}', flush=True)
                    return 1
                time.sleep(.05)
        os.dup2(descriptor, 9)
        inherited = True
        process = subprocess.Popen(command,
            env=dict(os.environ, LUOSHU_MIX_KERNEL_LOCK_HELD='1'), pass_fds=(9,),
            start_new_session=True)
        cancel_deadline = None
        while process.poll() is None:
            if interrupted and cancel_deadline is None:
                # The router's transaction runs in a shell subshell. Signalling
                # only its outer shell strands that subshell and the mapper.
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                cancel_deadline = time.monotonic() + 5
            if cancel_deadline is not None and time.monotonic() >= cancel_deadline:
                stop_group(process)
                break
            time.sleep(.05)
        return process.returncode if not interrupted else 128 + interrupted[0]
    finally:
        # Child ownership survives an abrupt parent death because FD 9 shares
        # this open file description. Closing parent FDs is not LOCK_UN.
        if inherited and descriptor != 9:
            os.close(9)
        os.close(descriptor)
        for sig, handler in old_handlers.items():
            signal.signal(sig, handler)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--module', type=Path, required=True)
    parser.add_argument('--lock', action='store_true')
    parser.add_argument('--wait', type=float, default=120)
    parser.add_argument('--request')
    parser.add_argument('--task')
    parser.add_argument('--progress', type=Path)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        parser.error('missing mapper command')
    if args.lock:
        return locked_run(args.module, command, args.wait)
    if not args.request or args.task is None or args.progress is None:
        parser.error('missing mapper request, task or progress file')
    return supervise(args.module, args.request, args.task, args.progress, command)


if __name__ == '__main__':
    raise SystemExit(main())
