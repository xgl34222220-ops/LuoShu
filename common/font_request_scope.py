#!/usr/bin/env python3
"""One synchronous read request, owned by an open caller stdin lease.

Worker stdin is /dev/null and close_fds=True. The caller closes its pipe on
cancellation/disconnect; only this finite supervisor reads that lease. stdout is
reserved for the worker protocol. Proven descendants are always reaped before
success, timeout or cancellation is returned; no detached generation is admitted.
"""
import argparse
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import time
import uuid

from task_scope import (Scope, clear_identity, identity_alive, load_identity,
                        recover, subreaper)


def recover_abandoned(directory):
    for path in directory.glob('*.pid.identity'):
        pidfile = Path(str(path)[:-len('.identity')])
        data = load_identity(pidfile)
        if data and not identity_alive(data):
            if not recover(data):
                raise RuntimeError('A previous inventory request still has uninterruptible owned processes')
            clear_identity(pidfile, data['token'])


def run(command, directory, timeout):
    directory.mkdir(parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    recover_abandoned(directory)
    token = uuid.uuid4().hex
    pidfile = directory / (token + '.pid')
    scope = Scope(pidfile, 'inventory-' + token, token)
    caught = []
    worker = None
    worker_status = None
    reason = 'error'
    started = time.monotonic()
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, lambda number, _frame: caught.append(number))

    def reap():
        nonlocal worker_status
        while True:
            try:
                pid, status = os.waitpid(-1, os.WNOHANG)
            except ChildProcessError:
                return
            if not pid:
                return
            if worker is not None and pid == worker.pid:
                worker_status = os.waitstatus_to_exitcode(status)
                # This function is the sole waitpid owner. Prevent Popen poll/__del__
                # from racing the subreaper or interpreting an already-reaped child.
                worker.returncode = worker_status

    code = 125
    cleaned = False
    try:
        subreaper()
        scope.publish()
        env = dict(os.environ, LUOSHU_TASK_SCOPE=token,
                   LUOSHU_TASK_OWNER_PID=str(os.getpid()),
                   LUOSHU_TASK_OWNER_START=str(scope.owner['start']),
                   LUOSHU_TASK_PID_FILE=str(pidfile))
        worker = subprocess.Popen(command, stdin=subprocess.DEVNULL, close_fds=True, env=env)
        scope.discover()
        scope.save(True)
        print('[font-request] ' + json.dumps({'event': 'started', 'token': token,
              'owner': scope.owner, 'worker': worker.pid, 'boot': scope.data['boot']}, separators=(',', ':')),
              file=sys.stderr, flush=True)
        deadline = started + timeout
        last_snapshot = time.monotonic()
        while True:
            reap()
            if worker_status is not None:
                reason = 'success' if worker_status == 0 else 'worker-error'
                code = worker_status if worker_status >= 0 else 128 - worker_status
                break
            if caught:
                reason, code = 'cancel', 128 + caught[0]
                break
            if time.monotonic() >= deadline:
                reason, code = 'timeout', 124
                break
            readable, _, _ = select.select([sys.stdin.fileno()], [], [], min(0.05, max(0, deadline - time.monotonic())))
            if readable and not os.read(sys.stdin.fileno(), 4096):
                reason, code = 'client-disconnect', 130
                break
            if time.monotonic() - last_snapshot >= 1.0:
                scope.discover()
                scope.save()
                last_snapshot = time.monotonic()
    except BaseException as exc:
        reason, code = 'error', 125
        print(f'[font-request] {type(exc).__name__}: {exc}', file=sys.stderr, flush=True)
    finally:
        cleaned = scope.cleanup(reap)
        if cleaned:
            clear_identity(pidfile, token)
        else:
            # Do not claim success, discard identities, or kill a numeric PID blindly.
            scope.save(True)
            code = 125
        if worker is not None and worker.returncode is None:
            worker.returncode = worker_status if worker_status is not None else -signal.SIGKILL
        print('[font-request] ' + json.dumps({'event': 'finished', 'token': token,
              'reason': reason, 'code': code, 'cleaned': cleaned,
              'elapsed_ms': round((time.monotonic() - started) * 1000, 3)}, separators=(',', ':')),
              file=sys.stderr, flush=True)
    return code


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--scope-dir', type=Path, required=True)
    parser.add_argument('--timeout', type=float, required=True)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command or not 0.05 <= args.timeout <= 120:
        parser.error('a command and a finite 0.05–120 second timeout are required')
    return run(command, args.scope_dir, args.timeout)


if __name__ == '__main__':
    raise SystemExit(main())
