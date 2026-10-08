#!/usr/bin/env python3
"""Real scoped font-lock lifecycle under mksh/dash and restricted procfs.

Usage: python3 scripts/font_lock_namespace_test.py [repository_or_package_root]
LUOSHU_TEST_MKSH may select an existing official mksh executable; absent mksh
is an error, never a skipped compatibility check. All modules, locks, records,
and payloads are temporary. Only bounded test-owned workers are supervised.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = (Path(sys.argv.pop(1)).resolve()
        if len(sys.argv) > 1 and not sys.argv[1].startswith('-')
        else Path(__file__).resolve().parents[1])
MKSH = os.environ.get('LUOSHU_TEST_MKSH') or shutil.which('mksh')
DASH = shutil.which('dash')
if not MKSH or not Path(MKSH).is_file() or not os.access(MKSH, os.X_OK):
    raise SystemExit('mksh is required: install the official package or set LUOSHU_TEST_MKSH')
if not DASH:
    raise SystemExit('dash is required for shell parity tests')
SHELLS = (('mksh', str(Path(MKSH).resolve())), ('dash', str(Path(DASH).resolve())))
MODES = ('normal', 'single-nspid', 'config-pid-ns-disabled')
REJECTED_MODES = ('permission-denied', 'nested-nspid', 'missing-capability')
FROZEN = json.loads(Path(__file__).with_name('stable111_frozen_runtime.json').read_text())['sha256']
OWNER_SUFFIXES = ('', '.owner.json', '.task', '.start', '.boot', '.ready')

# The identical adapter runs task_scope.py and the font-lock helper's inline
# stdin program. Thus restricted interfaces cannot accidentally be simulated
# in the supervisor alone while its worker still uses normal namespace links.
PYTHON_WRAPPER = r'''import errno, gzip, io, json, os, re, runpy, sys
from pathlib import Path
program, *arguments = sys.argv[1:]
mode = os.environ.get('LUOSHU_TEST_MODE', 'normal')
if program == '-':
    mode = os.environ.get('LUOSHU_TEST_INLINE_MODE', mode)
assert mode in ('normal', 'single-nspid', 'config-pid-ns-disabled', 'permission-denied', 'nested-nspid', 'missing-capability')
with open(os.environ['LUOSHU_TEST_AUDIT'], 'a') as audit:
    audit.write(json.dumps({'kind': 'stdin' if program == '-' else 'script', 'mode': mode}) + '\n')
real_readlink = os.readlink
def readlink(path, *args, **kwargs):
    value = os.fsdecode(path)
    if re.fullmatch(r'/proc/(?:self|[0-9]+)/ns/pid', value):
        if mode == 'permission-denied':
            raise PermissionError(errno.EACCES, 'fixture namespace denied', value)
        if mode != 'normal':
            raise FileNotFoundError(errno.ENOENT, 'fixture namespace unavailable', value)
    return real_readlink(path, *args, **kwargs)
os.readlink = readlink
real_read_text = Path.read_text
def read_text(path, *args, **kwargs):
    text = real_read_text(path, *args, **kwargs)
    if re.fullmatch(r'/proc/(?:self|[0-9]+)/status', str(path)):
        if mode in ('config-pid-ns-disabled', 'missing-capability'):
            text = ''.join(line for line in text.splitlines(keepends=True) if not line.startswith('NSpid:'))
        elif mode == 'nested-nspid':
            text = ''.join(('NSpid:\t1\t' + line.split()[-1] + '\n') if line.startswith('NSpid:') else line
                           for line in text.splitlines(keepends=True))
    return text
Path.read_text = read_text
real_gzip_open = gzip.open
def config(path, *args, **kwargs):
    if os.fsdecode(path) == '/proc/config.gz':
        if mode == 'config-pid-ns-disabled':
            return io.StringIO('# CONFIG_PID_NS is not set\n')
        if mode == 'missing-capability':
            raise FileNotFoundError(errno.ENOENT, 'fixture kernel capability unavailable', str(path))
    return real_gzip_open(path, *args, **kwargs)
gzip.open = config
sys.argv = [program, *arguments]
if program == '-':
    exec(compile(sys.stdin.read(), '<fixture inline python>', 'exec'), {'__name__': '__main__'})
else:
    runpy.run_path(program, run_name='__main__')
'''

MUTATOR = r'''import json, os, sys
from pathlib import Path
operation, variant = sys.argv[1:]
pidfile = Path(os.environ['LUOSHU_TASK_SCOPE_PIDFILE'])
root = Path(os.environ['LUOSHU_TEST_OUTPUT'])
backup = root / 'registration-backup.json'
suffixes = ('', '.owner.json', '.task', '.start', '.boot')
if operation == 'restore':
    for suffix, text in json.loads(backup.read_text()).items():
        target = Path(str(pidfile) + suffix)
        if target.is_symlink():
            target.unlink()
        target.write_text(text)
    raise SystemExit(0)
backup.write_text(json.dumps({suffix: Path(str(pidfile) + suffix).read_text() for suffix in suffixes}))
owner_path = Path(str(pidfile) + '.owner.json')
owner = json.loads(owner_path.read_text())
if variant == 'reused-start':
    owner['start'] = str(int(owner['start']) + 1000)
    Path(str(pidfile) + '.start').write_text(owner['start'] + '\n')
elif variant == 'task-mismatch':
    owner['task'] = 'unrelated-task'
    Path(str(pidfile) + '.task').write_text(owner['task'] + '\n')
elif variant == 'pid-mismatch':
    owner['procPid'] = 2147483647
elif variant == 'namespace-mismatch':
    owner['namespace'] = 'pid:[999999999]'
elif variant == 'owner-oversize':
    owner_path.write_text(json.dumps(owner) + ' ' * 65537)
    raise SystemExit(0)
elif variant in ('owner-symlink', 'sidecar-symlink'):
    target = owner_path if variant == 'owner-symlink' else Path(str(pidfile) + '.start')
    external = root / 'external-readonly-evidence'
    external.write_text(target.read_text())
    target.unlink()
    target.symlink_to(external)
    raise SystemExit(0)
else:
    raise SystemExit('unknown mutation')
owner_path.write_text(json.dumps(owner))
'''

WORKER = r'''#!/bin/sh
. "$MODDIR/common/font_switch_lock.sh" || exit 98
printf 'started\n' > "$LUOSHU_TEST_OUTPUT/worker-started"
if [ -n "${LUOSHU_TEST_MUTATION:-}" ]; then
    "$LUOSHU_TEST_REAL_PYTHON" "$LUOSHU_TEST_MUTATOR" mutate "$LUOSHU_TEST_MUTATION" || exit 97
fi
luoshu_font_lock_scope_identity capture > "$LUOSHU_TEST_OUTPUT/captured.conf"
capture_rc=$?
printf 'capture=%s\n' "$capture_rc" > "$LUOSHU_TEST_OUTPUT/result.conf"
luoshu_font_lock_acquire "$LUOSHU_TEST_LOCK" "$$"
acquire_rc=$?
printf 'acquire=%s\nreason=%s\n' "$acquire_rc" "${LUOSHU_FONT_LOCK_FAILURE_REASON:-}" >> "$LUOSHU_TEST_OUTPUT/result.conf"
luoshu_font_lock_failure_message > "$LUOSHU_TEST_OUTPUT/failure-message.txt"
if [ "$acquire_rc" -eq 0 ]; then
    cp "$LUOSHU_TEST_LOCK/pid" "$LUOSHU_TEST_OUTPUT/acquired-lock.conf" || exit 96
    if [ "$1" = release ]; then
        luoshu_font_lock_release "$LUOSHU_TEST_LOCK" "$$"
        release_rc=$?
        printf 'release=%s\n' "$release_rc" >> "$LUOSHU_TEST_OUTPUT/result.conf"
        [ "$release_rc" -eq 0 ] || acquire_rc=95
    fi
fi
if [ -n "${LUOSHU_TEST_MUTATION:-}" ]; then
    "$LUOSHU_TEST_REAL_PYTHON" "$LUOSHU_TEST_MUTATOR" restore "$LUOSHU_TEST_MUTATION" || exit 94
fi
exit "$acquire_rc"
'''


def snapshot(root):
    return {str(path.relative_to(root)): ('symlink', os.readlink(path)) if path.is_symlink()
            else ('file', path.read_bytes(), path.stat().st_mode) if path.is_file()
            else ('directory',) for path in root.rglob('*')}


def values(path):
    return dict(line.split('=', 1) for line in path.read_text().splitlines() if '=' in line)


class FontLockNamespaceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='luoshu-font-lock-ns-')
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.module = self.directory / 'module'
        common = self.module / 'common'
        common.mkdir(parents=True)
        (self.module / 'module.prop').write_text('id=LuoShu\n')
        for name in ('task_scope.py', 'task_scope.sh', 'font_switch_lock.sh', 'runtime_paths.sh',
                     'runtime_paths_lock.py', 'background_task.sh'):
            (common / name).symlink_to(ROOT / 'common' / name)
        self.python = self.directory / 'fixture-python'
        self.python.write_text('#!' + sys.executable + '\n' + PYTHON_WRAPPER)
        self.python.chmod(0o700)
        self.worker = self.directory / 'lock-worker.sh'
        self.worker.write_text(WORKER)
        self.mutator = self.directory / 'mutate-owner.py'
        self.mutator.write_text(MUTATOR)
        self.audit = self.directory / 'python-audit.jsonl'
        self.bin = self.directory / 'bin'
        self.bin.mkdir()
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith('LUOSHU_') and key not in ('MODDIR', 'MODULE_DIR', 'PYTHONHOME', 'PYTHONPATH')}
        self.env.update(MODDIR=str(self.module), MODULE_DIR=str(self.module),
                        LUOSHU_TASK_SCOPE_PYTHON=str(self.python), LUOSHU_RUNTIME_PATHS_PYTHON=sys.executable,
                        LUOSHU_TEST_AUDIT=str(self.audit), LUOSHU_TEST_REAL_PYTHON=sys.executable,
                        LUOSHU_TEST_MUTATOR=str(self.mutator))
        self.original_path = self.env.get('PATH', os.defpath)
        self.configure(SHELLS[0][1], 'normal')
        initialized = subprocess.run([self.shell, '-c',
            '. "$MODDIR/common/runtime_paths.sh"; luoshu_runtime_paths_init "$MODDIR"'],
            env=self.env, capture_output=True, text=True, timeout=10)
        self.assertEqual(initialized.returncode, 0, initialized.stdout + initialized.stderr)
        self.tasks = self.module / '.luoshu-state/tasks'
        self.lock = self.module / '.font_switch.lock'
        self.env['LUOSHU_TEST_LOCK'] = str(self.lock)
        self.counter = 0
        for relative in ('.luoshu-payload', '.luoshu-payload-next', '.luoshu-state/tmp/mix-stage'):
            target = self.module / relative
            (target / 'fonts').mkdir(parents=True)
            (target / 'fonts/preserved.ttf').write_bytes(b'\x00original fixture font\xff')
            (target / 'generation.conf').write_text('original-generation\n')
        self.payload_before = self.payloads()
        self.frozen_before = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in FROZEN}
        self.addCleanup(self.assert_payloads_and_frozen)

    def configure(self, shell, mode, *, inline_mode=None, mutation=None):
        self.shell = shell
        shim = self.bin / 'sh'
        shim.unlink(missing_ok=True)
        shim.symlink_to(shell)
        self.env['PATH'] = str(self.bin) + os.pathsep + self.original_path
        self.env['LUOSHU_TEST_MODE'] = mode
        for key, value in (('LUOSHU_TEST_INLINE_MODE', inline_mode), ('LUOSHU_TEST_MUTATION', mutation)):
            if value is None:
                self.env.pop(key, None)
            else:
                self.env[key] = value

    def payloads(self):
        return {name: snapshot(self.module / name) for name in
                ('.luoshu-payload', '.luoshu-payload-next', '.luoshu-state/tmp/mix-stage')}

    def assert_payloads_and_frozen(self):
        self.assertEqual(self.payloads(), self.payload_before)
        self.assertEqual({name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                          for name in FROZEN}, self.frozen_before)

    def expected_namespace(self, mode):
        if mode == 'normal':
            return os.readlink('/proc/self/ns/pid')
        info = os.stat('/proc')
        return 'procfs-single:%s:%s' % (info.st_dev, info.st_ino)

    def new_scope(self):
        self.counter += 1
        self.task = 'lock-fixture-' + str(self.counter)
        self.pidfile = self.tasks / (self.task + '.pid')
        self.output = self.directory / ('output-' + str(self.counter))
        self.output.mkdir()
        self.env['LUOSHU_TEST_OUTPUT'] = str(self.output)
        self.audit.write_text('')

    def run_scope(self, action='release', expected=0, *, launched=True):
        self.new_scope()
        result = subprocess.run([str(self.python), str(ROOT / 'common/task_scope.py'), 'run',
                                 '--pid-file', str(self.pidfile), '--task', self.task, '--timeout', '8', '--',
                                 self.shell, str(self.worker), action],
                                env=self.env, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        self.assertEqual((self.output / 'worker-started').exists(), launched)
        self.assert_payloads_and_frozen()
        if launched:
            proof = json.loads(Path(str(self.pidfile) + '.cleanup.json').read_text())
            self.assertIs(proof['cleaned'], True, proof)
            self.assertEqual(proof['result'], expected)
            self.assertEqual(proof['namespace'], self.expected_namespace(self.env['LUOSHU_TEST_MODE']))
            for key in ('leftoverPids', 'cleanupErrors', 'handoffTasks', 'handoffOwners'):
                self.assertEqual(proof[key], [])
            for suffix in OWNER_SUFFIXES:
                self.assertFalse(Path(str(self.pidfile) + suffix).exists(), suffix)
            audit = [json.loads(line) for line in self.audit.read_text().splitlines()]
            self.assertTrue(any(item['kind'] == 'script' and item['mode'] == self.env['LUOSHU_TEST_MODE'] for item in audit))
            self.assertTrue(any(item['kind'] == 'stdin' and item['mode'] == self.env.get('LUOSHU_TEST_INLINE_MODE', self.env['LUOSHU_TEST_MODE']) for item in audit))
            return values(self.output / 'result.conf')
        self.assertFalse(self.lock.exists())
        self.assertFalse(Path(str(self.pidfile) + '.owner.json').exists())
        return result

    def lock_command(self, code, *, expected, read_only=False, extra_env=None):
        before = snapshot(self.module) if read_only else None
        result = subprocess.run([self.shell, '-c', '. "$MODDIR/common/font_switch_lock.sh"\n' + code],
                                env=dict(self.env, **(extra_env or {})), capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        self.assertEqual(result.stderr, '')
        if read_only:
            self.assertEqual(snapshot(self.module), before, 'refusal must preserve lock and proof evidence')
        self.assert_payloads_and_frozen()
        return result

    def leave_completed_lock(self):
        state = self.run_scope('leave')
        self.assertEqual(state['capture'], '0')
        self.assertEqual(state['acquire'], '0')
        self.assertTrue((self.lock / 'pid').is_file())
        captured = values(self.output / 'captured.conf')
        self.assertEqual(captured['scope_namespace'], self.expected_namespace(self.env['LUOSHU_TEST_MODE']))
        return Path(str(self.pidfile) + '.cleanup.json')

    def reap(self):
        self.lock_command('luoshu_font_lock_scope_identity cleaned "$LUOSHU_TEST_LOCK"', expected=0, read_only=True)
        self.lock_command('luoshu_font_lock_reap_stale "$LUOSHU_TEST_LOCK"', expected=0)
        self.assertFalse(self.lock.exists())

    def assert_unconfirmed(self):
        self.lock_command('luoshu_font_lock_scope_identity cleaned "$LUOSHU_TEST_LOCK"', expected=1, read_only=True)
        self.lock_command('luoshu_font_lock_reap_stale "$LUOSHU_TEST_LOCK"', expected=1, read_only=True)
        self.assertTrue(self.lock.exists())

    def test_required_real_mksh_and_frozen_baseline(self):
        version = subprocess.run([MKSH, '-c', 'printf "%s\\n" "$KSH_VERSION"'], capture_output=True, text=True, timeout=5)
        self.assertIn('MIRBSD KSH', version.stdout)
        self.assertEqual(self.frozen_before, FROZEN)

    def test_full_scope_capture_acquire_release_in_both_shells(self):
        for mode in MODES:
            for name, shell in SHELLS:
                with self.subTest(mode=mode, shell=name):
                    self.configure(shell, mode)
                    state = self.run_scope()
                    self.assertEqual((state['capture'], state['acquire'], state['release']), ('0', '0', '0'))
                    self.assertFalse(self.lock.exists())
                    captured = values(self.output / 'captured.conf')
                    self.assertEqual(captured['scope_namespace'], self.expected_namespace(mode))
                    self.assertEqual(captured['scope_task'], self.task)
                    self.assertEqual(values(self.output / 'acquired-lock.conf')['scope_pidfile'], str(self.pidfile))

    def test_completed_scope_proof_safely_reaps_retained_lock(self):
        for mode in MODES:
            for name, shell in SHELLS:
                with self.subTest(mode=mode, shell=name):
                    self.configure(shell, mode)
                    proof = self.leave_completed_lock()
                    before = proof.read_bytes()
                    self.reap()
                    self.assertEqual(proof.read_bytes(), before)

    def test_supervisor_refuses_unverified_namespace_before_worker(self):
        for mode in REJECTED_MODES:
            for name, shell in SHELLS:
                with self.subTest(mode=mode, shell=name):
                    self.configure(shell, mode)
                    result = self.run_scope(expected=126, launched=False)
                    self.assertEqual(json.loads(result.stdout)['data']['reason'], 'proc-identity-unavailable')

    def test_inline_checker_refuses_unknown_permission_and_nested_identity(self):
        for mode in REJECTED_MODES:
            for name, shell in SHELLS:
                with self.subTest(mode=mode, shell=name):
                    self.configure(shell, 'normal', inline_mode=mode)
                    state = self.run_scope(expected=1)
                    self.assertEqual((state['capture'], state['acquire']), ('1', '1'))
                    self.assertEqual(state['reason'], 'scope-identity-unverified')
                    self.assertIn('字体切换锁身份验证失败', (self.output / 'failure-message.txt').read_text())
                    self.assertFalse(self.lock.exists())

    def test_capture_rejects_reused_pid_start_and_task_mismatches(self):
        for mutation in ('reused-start', 'pid-mismatch', 'task-mismatch', 'namespace-mismatch'):
            for mode in MODES:
                with self.subTest(mutation=mutation, mode=mode):
                    self.configure(SHELLS[0][1], mode, mutation=mutation)
                    state = self.run_scope(expected=1)
                    self.assertEqual((state['capture'], state['acquire']), ('1', '1'))
                    self.assertFalse(self.lock.exists())

    def test_capture_rejects_symlinks_and_oversized_owner(self):
        for mutation in ('owner-symlink', 'sidecar-symlink', 'owner-oversize'):
            for name, shell in SHELLS:
                with self.subTest(mutation=mutation, shell=name):
                    self.configure(shell, 'single-nspid', mutation=mutation)
                    state = self.run_scope(expected=1)
                    self.assertEqual((state['capture'], state['acquire']), ('1', '1'))
                    self.assertFalse(self.lock.exists())

    def test_scope_paths_outside_owned_task_tree_are_rejected(self):
        self.configure(SHELLS[0][1], 'normal')
        outside = self.directory / 'outside.pid'
        pid = os.getpid()
        start = Path('/proc/self/stat').read_text().rsplit(') ', 1)[1].split()[19]
        boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        owner = dict(pid=pid, procPid=pid, start=start, boot=boot, task='outside-fixture',
                     namespace=self.expected_namespace('normal'), pidfile=str(outside))
        for suffix, key in (('', 'pid'), ('.task', 'task'), ('.start', 'start'), ('.boot', 'boot')):
            Path(str(outside) + suffix).write_text(str(owner[key]) + '\n')
        Path(str(outside) + '.owner.json').write_text(json.dumps(owner))
        evidence = {suffix: Path(str(outside) + suffix).read_bytes()
                    for suffix in ('', '.task', '.start', '.boot', '.owner.json')}
        for name, shell in SHELLS:
            with self.subTest(shell=name):
                self.configure(shell, 'normal')
                self.lock_command('luoshu_font_lock_scope_identity capture', expected=1, read_only=True,
                                  extra_env={'LUOSHU_TASK_SCOPE_PIDFILE': str(outside),
                                             'LUOSHU_TASK_SCOPE_TASK': owner['task'],
                                             'LUOSHU_TASK_SCOPE_PID': str(pid)})
                self.assertEqual({suffix: Path(str(outside) + suffix).read_bytes()
                                  for suffix in evidence}, evidence)
        # A matching completed proof outside the task tree is also insufficient.
        proof = self.leave_completed_lock()
        original_lock = (self.lock / 'pid').read_text()
        outside_proof = self.directory / 'outside-completed.pid'
        Path(str(outside_proof) + '.cleanup.json').write_bytes(proof.read_bytes())
        (self.lock / 'pid').write_text(re.sub(r'^scope_pidfile=.*$',
            'scope_pidfile=' + str(outside_proof), original_lock, flags=re.M))
        self.assert_unconfirmed()
        (self.lock / 'pid').write_text(original_lock)
        self.reap()

    def test_real_live_owner_returns_busy_two_without_deletion(self):
        holder = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            start = Path('/proc/%s/stat' % holder.pid).read_text().rsplit(') ', 1)[1].split()[19]
            self.lock.mkdir()
            (self.lock / 'pid').write_text('%s\nstarttime=%s\nboot_id=%s\ntoken=owned-fixture\ncreated=%s\n' % (
                holder.pid, start, Path('/proc/sys/kernel/random/boot_id').read_text().strip(), int(time.time())))
            before = snapshot(self.lock)
            for name, shell in SHELLS:
                with self.subTest(shell=name):
                    self.configure(shell, 'single-nspid')
                    state = self.run_scope(expected=2)
                    self.assertEqual((state['capture'], state['acquire']), ('0', '2'))
                    self.assertEqual(snapshot(self.lock), before)
                    self.assertIsNone(holder.poll())
        finally:
            if holder.poll() is None:
                holder.terminate()
            holder.wait(timeout=5)

    def test_cleanup_proof_mismatches_fail_closed(self):
        changes = (('pid', 2147483647), ('start', '999999999999'), ('task', 'another-task'),
                   ('boot', '00000000-0000-4000-8000-000000000001'), ('namespace', 'pid:[99999]'),
                   ('cleaned', False), ('leftoverPids', [2147483647]), ('cleanupErrors', ['fixture error']),
                   ('handoffTasks', ['another-task']), ('handoffOwners', [{}]), ('schema', 'unknown-schema'))
        for mode in MODES:
            for name, shell in SHELLS:
                self.configure(shell, mode)
                proof_path = self.leave_completed_lock()
                original = proof_path.read_bytes()
                proof = json.loads(original)
                for key, value in changes:
                    with self.subTest(mode=mode, shell=name, field=key):
                        proof_path.write_text(json.dumps(dict(proof, **{key: value})))
                        self.assert_unconfirmed()
                        proof_path.write_bytes(original)
                self.reap()

    def test_new_owner_registration_blocks_old_cleanup_proof(self):
        for mode in MODES:
            for name, shell in SHELLS:
                with self.subTest(mode=mode, shell=name):
                    self.configure(shell, mode)
                    self.leave_completed_lock()
                    replacement = Path(str(self.pidfile) + '.owner.json')
                    replacement.write_text('{"task":"replacement-owner"}')
                    self.assert_unconfirmed()
                    replacement.unlink()
                    self.reap()

    def test_cleanup_proof_symlink_oversize_and_invalid_json_are_preserved(self):
        self.configure(SHELLS[0][1], 'single-nspid')
        proof = self.leave_completed_lock()
        original = proof.read_bytes()
        proof.unlink()
        self.assert_unconfirmed()
        proof.write_bytes(original)
        external = self.directory / 'external-proof.json'
        external.write_bytes(original)
        proof.unlink()
        proof.symlink_to(external)
        self.assert_unconfirmed()
        self.assertEqual(external.read_bytes(), original)
        proof.unlink()
        for content in (original + b' ' * 65537, b'{invalid json', b'[]'):
            with self.subTest(content=content[:20]):
                proof.write_bytes(content)
                self.assert_unconfirmed()
        proof.write_bytes(original)
        self.reap()

    def test_unverified_identity_does_not_reap_completed_lock(self):
        self.configure(SHELLS[0][1], 'normal')
        self.leave_completed_lock()
        for mode in REJECTED_MODES:
            for name, shell in SHELLS:
                with self.subTest(mode=mode, shell=name):
                    self.configure(shell, 'normal', inline_mode=mode)
                    self.assert_unconfirmed()
        self.configure(SHELLS[0][1], 'normal')
        self.reap()

    def test_reap_exact_record_check_preserves_replacement_token(self):
        self.configure(SHELLS[0][1], 'single-nspid')
        self.leave_completed_lock()
        old = (self.lock / 'pid').read_text().rstrip('\n')
        newer = re.sub(r'^token=.*$', 'token=replacement-token', old, flags=re.M) + '\n'
        (self.lock / 'pid').write_text(newer)
        # Pre-create the stable guard so the refusal snapshot includes it.
        (self.tasks / 'font-switch-reap.lock').touch(mode=0o600)
        self.lock_command('luoshu_font_lock_scope_identity reap "$LUOSHU_TEST_LOCK" "$LUOSHU_TEST_EXPECTED"',
                          expected=1, read_only=True, extra_env={'LUOSHU_TEST_EXPECTED': old})
        self.assertEqual((self.lock / 'pid').read_text(), newer)

    def test_borrowed_live_supervisor_environment_fails_ancestry_check(self):
        for name, shell in SHELLS:
            with self.subTest(shell=name):
                self.configure(shell, 'single-nspid')
                self.new_scope()
                process = subprocess.Popen([str(self.python), str(ROOT / 'common/task_scope.py'), 'run',
                    '--pid-file', str(self.pidfile), '--task', self.task, '--timeout', '5', '--',
                    sys.executable, '-c', 'import time; time.sleep(2)'],
                    env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                try:
                    deadline = time.monotonic() + 3
                    while not Path(str(self.pidfile) + '.ready').exists():
                        self.assertIsNone(process.poll(), 'scope exited before fixture readiness')
                        self.assertLess(time.monotonic(), deadline)
                        time.sleep(.01)
                    owner = json.loads(Path(str(self.pidfile) + '.owner.json').read_text())
                    self.lock_command('luoshu_font_lock_scope_identity capture', expected=1, read_only=True,
                                      extra_env={'LUOSHU_TASK_SCOPE_PIDFILE': str(self.pidfile),
                                                 'LUOSHU_TASK_SCOPE_TASK': self.task,
                                                 'LUOSHU_TASK_SCOPE_PID': str(owner['pid'])})
                    out, err = process.communicate(timeout=10)
                    self.assertEqual(process.returncode, 0, out + err)
                finally:
                    if process.poll() is None:
                        process.terminate()
                        process.communicate(timeout=10)

    def test_engine_distinguishes_validation_failure_from_busy(self):
        engine = (ROOT / 'common/legacy_v14_4/font_mix_engine.sh').read_text()
        definitions = []
        for name in ('apply_mix', '_mix_apply'):
            match = re.search(r'(?ms)^' + name + r'\(\) \{.*?^\}', engine)
            self.assertIsNotNone(match, name)
            definitions.append(match.group(0))
        harness = self.directory / 'engine-apply-harness.sh'
        harness.write_text('. "$MODDIR/common/font_switch_lock.sh"\n'
                           '. "$LUOSHU_TEST_MIX_PHASE_HELPER"\n' + '\n'.join(definitions) + r'''
set_mix_error() { printf '%s\n' "$1"; }
luoshu_font_lock_acquire() { LUOSHU_FONT_LOCK_FAILURE_REASON="$LUOSHU_TEST_FAILURE_REASON"; return "$LUOSHU_TEST_ACQUIRE_RC"; }
recover_interrupted_payload() { printf 'unexpected payload work\n' >&2; exit 99; }
LUOSHU_CONTINUOUS_SWITCH=1
LOCK_FILE="$LUOSHU_TEST_LOCK"
apply_mix cjk latin digit
exit $?
''')
        for name, shell in SHELLS:
            for acquire_rc, reason, message in (
                    ('2', '', '字体切换锁被占用或等待清理'),
                    ('1', 'scope-identity-unverified', '字体切换锁身份验证失败'),
                    ('1', '', '无法创建或验证字体切换锁')):
                with self.subTest(shell=name, acquire_rc=acquire_rc, reason=reason):
                    self.configure(shell, 'normal')
                    before = snapshot(self.module)
                    result = subprocess.run([shell, str(harness)],
                        env=dict(self.env, LUOSHU_TEST_ACQUIRE_RC=acquire_rc, LUOSHU_TEST_FAILURE_REASON=reason,
                                 LUOSHU_TEST_MIX_PHASE_HELPER=str(ROOT / 'common/legacy_v14_4/mix_phase_timing.sh')),
                        capture_output=True, text=True, timeout=5)
                    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                    self.assertEqual(result.stderr, '')
                    self.assertIn(message, result.stdout)
                    self.assertEqual(snapshot(self.module), before)


if __name__ == '__main__':
    unittest.main()
