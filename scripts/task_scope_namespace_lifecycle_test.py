#!/usr/bin/env python3
"""Exercise missing PID-namespace interfaces with real, test-owned processes.

Usage: python3 scripts/task_scope_namespace_lifecycle_test.py [module_root]

The child runner executes the selected common/task_scope.py with runpy. Only
the missing namespace-link interface is simulated; the older-kernel variant
also removes NSpid from real status reads and supplies an explicit disabled
kernel option. PID mappings, native procfs, process trees, signals, and reaping
remain real. Nothing is installed and no production bypass is introduced.
"""
import ctypes
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = (Path(sys.argv.pop(1)).resolve()
        if len(sys.argv) > 1 and not sys.argv[1].startswith('-')
        else Path(__file__).resolve().parents[1])
PROGRAM = ROOT / 'common/task_scope.py'
MODES = ('single-nspid', 'config-pid-ns-disabled')
OWNER_SUFFIXES = ('', '.task', '.start', '.boot', '.ready', '.owner.json', '.children')


RUNNER = r'''import errno, gzip, io, os, re, runpy, sys
from pathlib import Path

mode, program, *arguments = sys.argv[1:]
if mode not in ('single-nspid', 'config-pid-ns-disabled'):
    raise SystemExit('unknown test runner mode')
real_readlink = os.readlink
def missing_namespace(path, *args, **kwargs):
    if re.fullmatch(r'/proc/(?:self|[0-9]+)/ns/pid', os.fsdecode(path)):
        raise FileNotFoundError(errno.ENOENT, 'test: namespace link absent', str(path))
    return real_readlink(path, *args, **kwargs)
os.readlink = missing_namespace

if mode == 'config-pid-ns-disabled':
    real_read_text = Path.read_text
    def no_nspid(path, *args, **kwargs):
        text = real_read_text(path, *args, **kwargs)
        if re.fullmatch(r'/proc/(?:self|[0-9]+)/status', str(path)):
            text = ''.join(line for line in text.splitlines(keepends=True)
                           if not line.startswith('NSpid:'))
        return text
    Path.read_text = no_nspid
    real_gzip_open = gzip.open
    def disabled_pid_namespaces(path, *args, **kwargs):
        if os.fsdecode(path) == '/proc/config.gz':
            return io.StringIO('# CONFIG_PID_NS is not set\n')
        return real_gzip_open(path, *args, **kwargs)
    gzip.open = disabled_pid_namespaces

sys.argv = [program, *arguments]
runpy.run_path(program, run_name='__main__')
'''


WORKER = r'''import json, os, signal, subprocess, sys, time
from pathlib import Path

directory = Path(sys.argv[1])
mode = sys.argv[2]
directory.mkdir(parents=True, exist_ok=True)
def publish(name):
    fields = Path('/proc/self/stat').read_text().rsplit(') ', 1)[1].split()
    record = {'pid': os.getpid(), 'procPid': int(os.readlink('/proc/self')),
              'start': fields[19]}
    path = directory / ('fixture-' + name + '.json')
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(record))
    temporary.replace(path)

def leaf(name):
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    publish(name)
    while True:
        time.sleep(.02)

if mode == 'leaf':
    leaf('ordinary')
if mode == 'escape':
    publish('intermediate')
    if os.fork() != 0:
        os._exit(0)
    os.setsid()
    leaf('escaped')

publish('worker')
Path(os.environ['LUOSHU_TASK_SCOPE_TMPDIR'], 'owned.tmp').write_text('fixture')
if mode == 'nested':
    runner, compatibility, program = sys.argv[3:]
    nested = subprocess.Popen([
        sys.executable, runner, compatibility, program, 'run',
        '--pid-file', str(directory / 'nested.pid'), '--task', 'nested-task',
        '--timeout', '20', '--', sys.executable, __file__,
        str(directory / 'inner'), 'hold'])
else:
    ordinary = subprocess.Popen([sys.executable, __file__, str(directory), 'leaf'])
    intermediate = subprocess.Popen([sys.executable, __file__, str(directory), 'escape'],
                                    start_new_session=True)
    deadline = time.monotonic() + 5
    while not all((directory / ('fixture-' + name + '.json')).exists()
                  for name in ('ordinary', 'escaped')):
        if time.monotonic() >= deadline:
            raise SystemExit('fixture children did not start')
        time.sleep(.01)
    if mode == 'complete':
        raise SystemExit(0)

while True:
    time.sleep(.02)
'''


def process_record(pid):
    try:
        value = Path('/proc', str(pid), 'stat').read_text()
    except FileNotFoundError:
        return None
    fields = value.rsplit(') ', 1)[1].split()
    return {'pid': pid, 'procPid': int(value.split(' ', 1)[0]), 'start': fields[19]}


class MissingNamespaceLifecycleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not sys.platform.startswith('linux'):
            raise unittest.SkipTest('real procfs lifecycle tests require Linux')
        if int(os.readlink('/proc/self')) != os.getpid():
            raise unittest.SkipTest('native one-to-one /proc PID mapping required')
        fields = dict(line.split(':', 1) for line in Path('/proc/self/status').read_text().splitlines()
                      if ':' in line)
        if list(map(int, fields.get('NSpid', '').split())) != [os.getpid()]:
            raise unittest.SkipTest('single-NSpid native test environment required')
        if not PROGRAM.is_file():
            raise AssertionError('selected module has no common/task_scope.py: ' + str(PROGRAM))
        # This affects this test process only. It lets failure cleanup reap
        # fixture descendants if a broken supervisor exits before doing so.
        cls.libc = ctypes.CDLL(None, use_errno=True)
        cls.original_subreaper = ctypes.c_int()
        if cls.libc.prctl(37, ctypes.byref(cls.original_subreaper), 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), 'PR_GET_CHILD_SUBREAPER failed')
        if cls.libc.prctl(36, 1, 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), 'PR_SET_CHILD_SUBREAPER failed')

    @classmethod
    def tearDownClass(cls):
        if cls.libc.prctl(36, cls.original_subreaper.value, 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), 'restoring test subreaper failed')

    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='task-scope-missing-ns-')
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.runner = self.directory / 'namespace_runner.py'
        self.runner.write_text(RUNNER)
        self.fixture = self.directory / 'fixture_worker.py'
        self.fixture.write_text(WORKER)
        self.pidfile = self.directory / 'scope.pid'
        self.env = {name: value for name, value in os.environ.items()
                    if not name.startswith('LUOSHU_')}
        self.env['LUOSHU_TMP_DIR'] = str(self.directory / 'tmp')
        info = os.stat('/proc')
        self.namespace = 'procfs-single:%s:%s' % (info.st_dev, info.st_ino)
        self.processes = []
        self.logs = []
        self.addCleanup(self.cleanup_processes)
        self.sentinel = self.spawn([sys.executable, '-c', 'import time; time.sleep(90)',
                                   'unrelated-owned-task-sentinel'])

    def spawn(self, arguments):
        log = (self.directory / ('process-%s.log' % len(self.logs))).open('w+')
        self.logs.append(log)
        process = subprocess.Popen(arguments, env=self.env, stdout=log, stderr=log)
        self.processes.append((process, process_record(process.pid)))
        return process

    def command(self, mode, *arguments):
        return [sys.executable, str(self.runner), mode, str(PROGRAM), *map(str, arguments)]

    def diagnostics(self):
        output = []
        for log in self.logs:
            log.flush()
            log.seek(0)
            output.append(log.read())
        return '\n'.join(output)

    def wait_for(self, condition, timeout=6):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if condition():
                return
            time.sleep(.02)
        self.fail('fixture readiness timed out\n' + self.diagnostics())

    def start(self, mode, action='hold', timeout=20):
        worker = [sys.executable, str(self.fixture), str(self.directory), action]
        if action == 'nested':
            worker += [str(self.runner), mode, str(PROGRAM)]
        process = self.spawn(self.command(mode, 'run', '--pid-file', self.pidfile,
                                         '--task', 'owned-task', '--timeout', timeout,
                                         '--', *worker))
        fixture_root = self.directory / 'inner' if action == 'nested' else self.directory
        self.wait_for(lambda: all((fixture_root / ('fixture-' + name + '.json')).exists()
                                 for name in ('ordinary', 'escaped')))
        if action == 'nested':
            self.wait_for(lambda: Path(str(self.directory / 'nested.pid') + '.ready').exists())
            self.assertTrue(list(Path(str(self.pidfile) + '.children').glob('*.json')))
        return process

    def action(self, mode, action, pidfile=None, task='owned-task', expected=0):
        result = subprocess.run(self.command(mode, action, pidfile or self.pidfile, task),
                                env=self.env, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr + self.diagnostics())
        return result

    def assert_proof(self, mode, pidfile, task, result, reason=None):
        proof = json.loads(Path(str(pidfile) + '.cleanup.json').read_text())
        self.assertEqual(proof['schema'], 'task-cleanup-v2')
        self.assertEqual(proof['namespace'], self.namespace)
        self.assertEqual(proof['task'], task)
        self.assertEqual(proof['result'], result)
        if reason is not None:
            self.assertEqual(proof['reason'], reason)
        self.assertIs(proof['cleaned'], True)
        self.assertEqual(proof['leftoverPids'], [])
        self.assertFalse(proof.get('cleanupErrors'))
        self.assertEqual(proof['handoffTasks'], [])
        self.assertEqual(proof['handoffOwners'], [])
        self.assertEqual(proof['boot'], Path('/proc/sys/kernel/random/boot_id').read_text().strip())
        for suffix in OWNER_SUFFIXES:
            self.assertFalse(Path(str(pidfile) + suffix).exists(), 'stale owner: ' + suffix)
        self.action(mode, 'cleaned', pidfile, task)
        self.action(mode, 'settled', pidfile, task)
        self.action(mode, 'alive', pidfile, task, expected=1)
        cancellation = json.loads(self.action(mode, 'cancel', pidfile, task).stdout)
        self.assertEqual(cancellation['status'], 'ok')
        self.assertIs(cancellation['data']['cleaned'], True)
        for suffix in OWNER_SUFFIXES:
            self.assertFalse(Path(str(pidfile) + suffix).exists(), 'inspection recreated owner: ' + suffix)
        return proof

    def assert_clean(self, mode, process, result, reason):
        self.assertEqual(process.wait(timeout=10), result, self.diagnostics())
        proof = self.assert_proof(mode, self.pidfile, 'owned-task', result, reason)
        self.assertGreaterEqual(proof['reaped'], 2)
        self.assertFalse(list((self.directory / 'tmp').glob('task-*')))
        records = list(self.directory.rglob('fixture-*.json'))
        self.assertGreaterEqual(len(records), 4)
        for path in records:
            record = json.loads(path.read_text())
            current = process_record(record['procPid'])
            self.assertTrue(current is None or current['start'] != record['start'],
                            'fixture was not fully reaped: ' + path.name)
        self.assertIsNone(self.sentinel.poll(), 'unrelated sentinel was signalled')

    def exercise(self, mode, action):
        if action == 'complete':
            self.assert_clean(mode, self.start(mode, 'complete'), 0, 'completed')
        elif action == 'timeout':
            self.assert_clean(mode, self.start(mode, timeout=1.5), 124, 'timeout')
        else:
            process = self.start(mode, 'nested' if action == 'nested' else 'hold')
            owner = json.loads(Path(str(self.pidfile) + '.owner.json').read_text())
            self.assertEqual(owner['namespace'], self.namespace)
            self.action(mode, 'alive')
            result = json.loads(self.action(mode, 'cancel').stdout)
            self.assertEqual(result['status'], 'ok')
            self.assertIs(result['data']['cleaned'], True)
            self.assert_clean(mode, process, 143, 'cancelled')
            if action == 'nested':
                self.assert_proof(mode, self.directory / 'nested.pid', 'nested-task', 143)

    def cleanup_processes(self):
        # Stop only Popen children and identity records written by our fixtures.
        # The sentinel remains alive until all behavioral assertions have run.
        for process, _ in reversed(self.processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
        records = [record for _, record in self.processes if record]
        for path in list(self.directory.rglob('fixture-*.json')) + list(self.directory.rglob('*.owner.json')):
            try:
                records.append(json.loads(path.read_text()))
            except (OSError, ValueError):
                continue
        for record in records:
            pid = record['pid']
            if pid <= 1 or pid != record['procPid']:
                continue
            current = process_record(pid)
            if current and current['start'] == record['start']:
                descriptor = None
                try:
                    if hasattr(os, 'pidfd_open') and hasattr(signal, 'pidfd_send_signal'):
                        descriptor = os.pidfd_open(pid)
                        if process_record(pid) == current:
                            signal.pidfd_send_signal(descriptor, signal.SIGKILL)
                    elif process_record(pid) == current:
                        os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                finally:
                    if descriptor is not None:
                        os.close(descriptor)
            try:
                os.waitpid(pid, 0)
            except ChildProcessError:
                pass
        for log in self.logs:
            log.close()


def lifecycle_test(mode, action):
    def test(self):
        self.exercise(mode, action)
    test.__doc__ = '%s lifecycle with %s compatibility evidence.' % (action, mode)
    return test


for _mode in MODES:
    for _action in ('complete', 'timeout', 'cancel', 'nested'):
        setattr(MissingNamespaceLifecycleTest, 'test_' + _mode.replace('-', '_') + '_' + _action,
                lifecycle_test(_mode, _action))


if __name__ == '__main__':
    unittest.main(verbosity=2)
