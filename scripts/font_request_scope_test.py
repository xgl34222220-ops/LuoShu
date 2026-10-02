#!/usr/bin/env python3
"""Proof for the synchronous App lease protocol, separate from detached task tests."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'common/font_request_scope.py'
WORKER = r'''
import json, os, signal, sys, time
from pathlib import Path
out=Path(sys.argv[1]); mode=sys.argv[2]
def record():
    data=Path('/proc/self/stat').read_text().rsplit(') ',1)[1].split()
    with out.open('a') as f: f.write(json.dumps({'pid':os.getpid(),'start':int(data[19]),'token':os.environ['LUOSHU_TASK_SCOPE']})+'\n')
record()
# stdin must be replaced, rather than inheriting the caller lease.
assert os.read(0, 1) == b''
child=os.fork()
if child==0:
    os.setsid()
    second=os.fork()
    if second>0: os._exit(0)
    record()
    def late(*_):
        pid=os.fork()
        if pid==0:
            signal.signal(signal.SIGTERM,signal.SIG_IGN); record()
            while True: time.sleep(.1)
        signal.signal(signal.SIGTERM,signal.SIG_IGN)
    signal.signal(signal.SIGTERM,late)
    while True: time.sleep(.1)
time.sleep(.15)
if mode=='success': sys.exit(0)
if mode=='error': sys.exit(7)
while True: time.sleep(.1)
'''


def alive(record):
    try:
        fields = Path(f'/proc/{record["pid"]}/stat').read_text().rsplit(') ', 1)[1].split()
        return int(fields[19]) == record['start'] # Zombies also fail the reaping gate.
    except FileNotFoundError:
        return False


class RequestScopeTest(unittest.TestCase):
    def case(self, mode, expected):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            records = base / 'workers.jsonl'
            worker = base / 'worker.py'
            worker.write_text(WORKER)
            # A same-program, unrelated process must survive every scope cleanup.
            sentinel = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])
            try:
                with (base / 'out').open('w') as output, (base / 'log').open('w') as log:
                    request = subprocess.Popen([sys.executable, str(HELPER), '--scope-dir', str(base / 'scope'),
                        '--timeout', '0.6' if mode == 'timeout' else '10', '--', sys.executable, str(worker), str(records), mode],
                        stdin=subprocess.PIPE, stdout=output, stderr=log)
                    deadline = time.monotonic() + 5
                    while time.monotonic() < deadline and (not records.exists() or len(records.read_text().splitlines()) < 2):
                        time.sleep(.01)
                    self.assertTrue(records.exists())
                    if mode == 'cancel': request.send_signal(signal.SIGTERM)
                    if mode == 'disconnect': request.stdin.close()
                    code = request.wait(timeout=9)
                    if not request.stdin.closed: request.stdin.close()
                self.assertEqual(expected, code, (base / 'log').read_text())
                events = [json.loads(line.split(' ', 1)[1]) for line in (base / 'log').read_text().splitlines()
                          if line.startswith('[font-request] {')]
                self.assertTrue(events[-1]['cleaned'])
                self.assertEqual('finished', events[-1]['event'])
                children = [json.loads(line) for line in records.read_text().splitlines()]
                self.assertGreaterEqual(len(children), 2)
                self.assertEqual(1, len({row['token'] for row in children}))
                self.assertFalse(any(alive(row) for row in children), children)
                self.assertEqual([], list((base / 'scope').iterdir()))
                self.assertIsNone(sentinel.poll())
                print(f'SYNC_SCOPE {mode}: code={code} owned={len(children)} all_reaped=true sentinel_alive=true')
            finally:
                sentinel.terminate()
                sentinel.wait(timeout=3)

    def test_success_reaps_detached_descendants(self): self.case('success', 0)
    def test_worker_failure_reaps_detached_descendants(self): self.case('error', 7)
    def test_timeout_reaps_detached_descendants(self): self.case('timeout', 124)
    def test_signal_cancel_reaps_detached_descendants(self): self.case('cancel', 143)
    def test_caller_pipe_disconnect_reaps_detached_descendants(self): self.case('disconnect', 130)


if __name__ == '__main__':
    unittest.main(verbosity=2)
