#!/usr/bin/env python3
"""Hermetic /proc PID-namespace compatibility and fail-closed regressions.

Usage: python3 scripts/task_scope_namespace_test.py [repository_or_package_root]

Every /proc path is redirected into a temporary fixture before importing the
module. Process creation and all signaling entry points are blocked unless a
test replaces them with an in-memory recorder. No device or host owner record,
process identity, kernel configuration, or signal is used.
"""
import builtins
import contextlib
import ctypes
import errno
import gzip
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch


ROOT = (Path(sys.argv.pop(1)).resolve()
        if len(sys.argv) > 1 and not sys.argv[1].startswith('-')
        else Path(__file__).resolve().parents[1])
PROGRAM = ROOT / 'common/task_scope.py'
BOOT = '11111111-2222-4333-8444-555555555555'
OLD_BOOT = '00000000-0000-4000-8000-000000000001'
NS = 'pid:[4026531836]'
SELF_PID = 4100
TARGET_PID = 4200
MISSING = object()
REAL_OPEN = builtins.open
REAL_PATH_OPEN = Path.open
REAL_STAT = Path.stat
REAL_LSTAT = Path.lstat
REAL_ITERDIR = Path.iterdir
REAL_READLINK = os.readlink
REAL_OS_STAT = os.stat
REAL_SCANDIR = os.scandir


def stat_text(pid, parent, start, state='S'):
    # starttime is field 22 overall / index 19 after the closing comm bracket.
    fields = [state, str(parent)] + ['0'] * 17 + [str(start)] + ['0'] * 30
    return str(pid) + ' (fixture worker) ' + ' '.join(fields) + '\n'


class ProcFixture:
    def __init__(self, directory, *, namespace=NS, self_nspid=None, local_pid=SELF_PID):
        self.base = Path(directory)
        self.proc = self.base / 'proc'
        self.module = self.base / 'module'
        self.module.mkdir()
        self.local_pid = local_pid
        self.readlink_errors = {}
        self.open_errors = {}
        self.stat_errors = {}
        self.scandir_errors = {}
        self.iterdir_errors = {}
        self.reads = []
        self.links = []
        self.statfs_magic = 0x9fa0
        self.write('sys/kernel/random/boot_id', BOOT + '\n')
        self.add_process(SELF_PID, parent=1, start='100', namespace=namespace,
                         nspid=[SELF_PID] if self_nspid is None else self_nspid)
        (self.proc / 'self').symlink_to(str(SELF_PID))

    def write(self, relative, content):
        path = self.proc / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content)

    def add_process(self, pid, *, parent=SELF_PID, start='200', namespace=NS,
                    nspid=None, status_pid=None, stat_pid=None, state='S'):
        status_pid = pid if status_pid is None else status_pid
        stat_pid = pid if stat_pid is None else stat_pid
        lines = ['Name:\tfixture worker', 'State:\t' + state,
                 'Tgid:\t' + str(status_pid), 'Pid:\t' + str(status_pid),
                 'PPid:\t' + str(parent)]
        if nspid is not MISSING:
            nspid = [pid] if nspid is None else nspid
            lines.append('NSpid:\t' + '\t'.join(map(str, nspid)))
        self.write(str(pid) + '/status', '\n'.join(lines) + '\n')
        self.write(str(pid) + '/stat', stat_text(stat_pid, parent, start, state))
        if namespace is not MISSING:
            path = self.proc / str(pid) / 'ns/pid'
            path.parent.mkdir(parents=True, exist_ok=True)
            path.symlink_to(namespace)

    def configuration(self, text):
        self.write('config.gz', gzip.compress(text.encode()))

    def redirected(self, path):
        if isinstance(path, int):
            return path
        value = os.fsdecode(path)
        if value == '/proc' or value.startswith('/proc/'):
            return self.proc / value.lstrip('/').removeprefix('proc').lstrip('/')
        return path

    def open(self, path, *args, **kwargs):
        value = os.fsdecode(path) if not isinstance(path, int) else None
        self.reads.append(value)
        if value in self.open_errors:
            raise self.open_errors[value]
        return REAL_OPEN(self.redirected(path), *args, **kwargs)

    def path_open(self, path, *args, **kwargs):
        value = str(path)
        self.reads.append(value)
        if value in self.open_errors:
            raise self.open_errors[value]
        return REAL_PATH_OPEN(Path(self.redirected(path)), *args, **kwargs)

    def readlink(self, path, *args, **kwargs):
        value = os.fsdecode(path)
        self.links.append(value)
        if value in self.readlink_errors:
            raise self.readlink_errors[value]
        return REAL_READLINK(self.redirected(path), *args, **kwargs)

    def os_stat(self, path, *args, **kwargs):
        if not isinstance(path, int) and os.fsdecode(path) in self.stat_errors:
            raise self.stat_errors[os.fsdecode(path)]
        return REAL_OS_STAT(self.redirected(path), *args, **kwargs)

    def scandir(self, path):
        if not isinstance(path, int) and os.fsdecode(path) in self.scandir_errors:
            raise self.scandir_errors[os.fsdecode(path)]
        return REAL_SCANDIR(self.redirected(path))

    def iterdir(self, path):
        if str(path) in self.iterdir_errors:
            raise self.iterdir_errors[str(path)]
        logical = Path(path)
        physical = Path(self.redirected(path))
        if physical == logical:
            return REAL_ITERDIR(path)
        return (logical / child.name for child in REAL_ITERDIR(physical))

    @contextlib.contextmanager
    def active(self):
        with contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(builtins, 'open', self.open))
            stack.enter_context(patch.object(Path, 'open', lambda path, *a, **k: self.path_open(path, *a, **k)))
            stack.enter_context(patch.object(Path, 'stat', lambda path, *a, **k: REAL_STAT(Path(self.redirected(path)), *a, **k)))
            stack.enter_context(patch.object(Path, 'lstat', lambda path, *a, **k: REAL_LSTAT(Path(self.redirected(path)), *a, **k)))
            stack.enter_context(patch.object(Path, 'iterdir', lambda path: self.iterdir(path)))
            stack.enter_context(patch.object(os, 'stat', self.os_stat))
            stack.enter_context(patch.object(os, 'scandir', self.scandir))
            def statfs(path, buffer):
                if path != b'/proc':
                    raise AssertionError('unexpected native filesystem query')
                ctypes.cast(buffer, ctypes.POINTER(ctypes.c_long))[0] = self.statfs_magic
                return 0
            stack.enter_context(patch.object(ctypes, 'CDLL', return_value=SimpleNamespace(statfs=statfs, prctl=lambda *args: 0)))
            stack.enter_context(patch.object(os, 'readlink', self.readlink))
            stack.enter_context(patch.object(os, 'getpid', return_value=self.local_pid))
            for name in ('kill', 'killpg', 'pidfd_open'):
                if hasattr(os, name):
                    stack.enter_context(patch.object(os, name, side_effect=AssertionError('real os.' + name + ' forbidden')))
            if hasattr(signal, 'pidfd_send_signal'):
                stack.enter_context(patch.object(signal, 'pidfd_send_signal', side_effect=AssertionError('real pidfd signal forbidden')))
            stack.enter_context(patch.object(subprocess, 'Popen', side_effect=AssertionError('real process creation forbidden')))
            yield

    def load(self):
        spec = importlib.util.spec_from_file_location('namespace_scope_under_test', PROGRAM)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


class NamespaceCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='luoshu-proc-namespace-test-')
        self.addCleanup(self.temporary.cleanup)

    def fixture(self, **kwargs):
        return ProcFixture(self.temporary.name, **kwargs)

    def invoke(self, scope, *args):
        with patch.object(sys, 'argv', [str(PROGRAM), *map(str, args)]), \
                contextlib.redirect_stdout(io.StringIO()) as output, \
                contextlib.redirect_stderr(io.StringIO()) as errors:
            code = scope.main()
        self.assertNotIn('Traceback', errors.getvalue())
        messages = [json.loads(line) for line in output.getvalue().splitlines() if line.strip()]
        return code, messages, errors.getvalue()

    def register(self, fixture, *, record=None, legacy=False):
        pidfile = fixture.module / 'config/mix_worker.pid'
        pidfile.parent.mkdir(parents=True, exist_ok=True)
        record = record or dict(procPid=TARGET_PID, pid=TARGET_PID, parent=SELF_PID,
                                state='S', start='200', namespace=NS, boot=BOOT)
        record = dict(record, task='fixture-task', pidfile=str(pidfile))
        for suffix, key in (('', 'pid'), ('.task', 'task'), ('.start', 'start'), ('.boot', 'boot')):
            Path(str(pidfile) + suffix).write_text(str(record[key]) + '\n')
        if not legacy:
            Path(str(pidfile) + '.owner.json').write_text(json.dumps(record))
        return pidfile, record

    @staticmethod
    def snapshot(fixture):
        return {str(path.relative_to(fixture.module)): path.read_bytes()
                for path in fixture.module.rglob('*') if path.is_file()}

    def assert_unknown(self, fixture, scope, pid=TARGET_PID):
        unavailable = getattr(scope, 'IdentityUnavailable', None)
        self.assertIsNotNone(unavailable, 'unverified identity must be distinct from an absent process')
        with self.assertRaises(unavailable):
            scope.identity(pid)

    def assert_cancel_preserves(self, fixture, scope, pidfile):
        before = self.snapshot(fixture)
        code, messages, _ = self.invoke(scope, 'cancel-all', fixture.module)
        self.assertIn(code, (125, 126))
        self.assertEqual(self.snapshot(fixture), before, 'uncertain ownership evidence must be preserved byte-for-byte')
        self.assertTrue(messages, 'refusal must have structured output')
        self.assertTrue(any(m.get('status') == 'error' and m.get('data', {}).get('cleaned') is False
                            for m in messages), messages)

    def test_normal_namespace_identity_and_pid_translation_are_unchanged(self):
        fixture = self.fixture(self_nspid=[SELF_PID, 77], local_pid=77)
        fixture.add_process(TARGET_PID, nspid=[TARGET_PID, 88])
        with fixture.active():
            scope = fixture.load()
            self.assertEqual(scope.identity(TARGET_PID), dict(procPid=TARGET_PID, pid=88,
                             parent=SELF_PID, start='200', state='S', namespace=NS, boot=BOOT))
            self.assertNotIn('/proc/config.gz', fixture.reads)

    def test_normal_different_namespace_is_not_owned(self):
        fixture = self.fixture()
        fixture.add_process(TARGET_PID, namespace='pid:[different]')
        with fixture.active():
            self.assertIsNone(fixture.load().identity(TARGET_PID))

    def test_missing_self_namespace_does_not_crash_import(self):
        fixture = self.fixture(namespace=MISSING)
        with fixture.active():
            self.assertTrue(callable(fixture.load().main))

    def test_missing_namespace_empty_cancel_all_succeeds(self):
        fixture = self.fixture(namespace=MISSING)
        with fixture.active():
            code, _, _ = self.invoke(fixture.load(), 'cancel-all', fixture.module)
            self.assertEqual(code, 0)

    def test_unknown_namespace_empty_cancel_all_still_succeeds(self):
        fixture = self.fixture(namespace=MISSING, self_nspid=MISSING)
        with fixture.active():
            code, _, _ = self.invoke(fixture.load(), 'cancel-all', fixture.module)
            self.assertEqual(code, 0, 'an empty cancellation requires no process capability')

    def test_single_nspid_fallback_preserves_pid_start_and_boot(self):
        fixture = self.fixture(namespace=MISSING)
        fixture.add_process(TARGET_PID, namespace=MISSING)
        with fixture.active():
            scope = fixture.load()
            owner = scope.identity(SELF_PID)
            record = scope.identity(TARGET_PID)
            self.assertEqual({k: record[k] for k in ('procPid', 'pid', 'parent', 'start', 'state', 'boot')},
                             dict(procPid=TARGET_PID, pid=TARGET_PID, parent=SELF_PID,
                                  start='200', state='S', boot=BOOT))
            self.assertTrue(record['namespace'])
            self.assertEqual(owner['namespace'], record['namespace'])
            self.assertNotEqual(record['namespace'], NS)
            self.assertTrue(scope.same_process(record))

    def test_fallback_identity_is_stable_across_imports(self):
        fixture = self.fixture(namespace=MISSING)
        fixture.add_process(TARGET_PID, namespace=MISSING)
        with fixture.active():
            one = fixture.load().identity(TARGET_PID)
            two = fixture.load().identity(TARGET_PID)
            self.assertEqual(one, two)

    def test_fallback_signal_uses_exact_verified_pid_only(self):
        fixture = self.fixture(namespace=MISSING)
        fixture.add_process(TARGET_PID, namespace=MISSING)
        with fixture.active():
            scope = fixture.load()
            record = scope.identity(TARGET_PID)
            with contextlib.ExitStack() as stack:
                kill = stack.enter_context(patch.object(os, 'kill'))
                if hasattr(os, 'pidfd_open'):
                    stack.enter_context(patch.object(os, 'pidfd_open', side_effect=OSError(errno.ENOSYS, 'fixture')))
                self.assertTrue(scope.signal_record(record, signal.SIGTERM))
                kill.assert_called_once_with(TARGET_PID, signal.SIGTERM)

    def test_fallback_reused_pid_start_is_not_signaled(self):
        fixture = self.fixture(namespace=MISSING)
        fixture.add_process(TARGET_PID, namespace=MISSING)
        with fixture.active():
            scope = fixture.load()
            record = scope.identity(TARGET_PID)
            fixture.write(str(TARGET_PID) + '/stat', stat_text(TARGET_PID, SELF_PID, '999'))
            self.assertFalse(scope.same_process(record))
            self.assertFalse(scope.signal_record(record, signal.SIGTERM))

    def test_fallback_previous_boot_is_not_signaled(self):
        fixture = self.fixture(namespace=MISSING)
        fixture.add_process(TARGET_PID, namespace=MISSING)
        with fixture.active():
            scope = fixture.load()
            record = dict(scope.identity(TARGET_PID), boot=OLD_BOOT)
            self.assertFalse(scope.same_process(record))
            self.assertFalse(scope.signal_record(record, signal.SIGTERM))

    def test_fallback_mismatched_namespace_is_not_signaled(self):
        fixture = self.fixture(namespace=MISSING)
        fixture.add_process(TARGET_PID, namespace=MISSING)
        with fixture.active():
            scope = fixture.load()
            record = dict(scope.identity(TARGET_PID), namespace=NS)
            self.assertFalse(scope.same_process(record))
            self.assertFalse(scope.signal_record(record, signal.SIGTERM))

    def test_explicit_disabled_pid_namespaces_allow_missing_nspid(self):
        fixture = self.fixture(namespace=MISSING, self_nspid=MISSING)
        fixture.configuration('# CONFIG_PID_NS is not set\nCONFIG_NAMESPACES=y\n')
        fixture.add_process(TARGET_PID, namespace=MISSING, nspid=MISSING)
        with fixture.active():
            scope = fixture.load()
            record = scope.identity(TARGET_PID)
            self.assertEqual(record['pid'], TARGET_PID)
            self.assertEqual(record['start'], '200')
            self.assertEqual(record['boot'], BOOT)
            self.assertTrue(scope.same_process(record))

    def test_missing_nspid_without_kernel_evidence_is_unknown(self):
        fixture = self.fixture(namespace=MISSING, self_nspid=MISSING)
        fixture.add_process(TARGET_PID, namespace=MISSING, nspid=MISSING)
        with fixture.active():
            self.assert_unknown(fixture, fixture.load())

    def test_enabled_pid_namespaces_do_not_justify_missing_nspid(self):
        fixture = self.fixture(namespace=MISSING, self_nspid=MISSING)
        fixture.configuration('CONFIG_PID_NS=y\n')
        fixture.add_process(TARGET_PID, namespace=MISSING, nspid=MISSING)
        with fixture.active():
            self.assert_unknown(fixture, fixture.load())

    def test_unrelated_kernel_config_does_not_justify_missing_nspid(self):
        fixture = self.fixture(namespace=MISSING, self_nspid=MISSING)
        fixture.configuration('CONFIG_NAMESPACES=y\n# CONFIG_NET_NS is not set\n')
        fixture.add_process(TARGET_PID, namespace=MISSING, nspid=MISSING)
        with fixture.active():
            self.assert_unknown(fixture, fixture.load())

    def test_self_namespace_permission_denial_is_not_fallback(self):
        fixture = self.fixture()
        fixture.readlink_errors['/proc/self/ns/pid'] = PermissionError(errno.EACCES, 'fixture denial')
        fixture.add_process(TARGET_PID)
        with fixture.active():
            scope = fixture.load()
            self.assert_unknown(fixture, scope)
            pidfile, _ = self.register(fixture)
            self.assert_cancel_preserves(fixture, scope, pidfile)

    def test_target_namespace_permission_denial_is_unknown_and_preserved(self):
        fixture = self.fixture()
        fixture.add_process(TARGET_PID)
        fixture.readlink_errors[f'/proc/{TARGET_PID}/ns/pid'] = PermissionError(errno.EACCES, 'fixture denial')
        with fixture.active():
            scope = fixture.load()
            self.assert_unknown(fixture, scope)
            pidfile, _ = self.register(fixture)
            self.assert_cancel_preserves(fixture, scope, pidfile)

    def test_nested_self_nspid_is_not_fallback(self):
        fixture = self.fixture(namespace=MISSING, self_nspid=[SELF_PID, 77], local_pid=77)
        fixture.add_process(TARGET_PID, namespace=MISSING)
        with fixture.active():
            self.assert_unknown(fixture, fixture.load())

    def test_nested_target_nspid_is_not_fallback(self):
        fixture = self.fixture(namespace=MISSING)
        fixture.add_process(TARGET_PID, namespace=MISSING, nspid=[TARGET_PID, 88])
        with fixture.active():
            self.assert_unknown(fixture, fixture.load())

    def test_contradictory_self_proc_and_local_pid_is_not_fallback(self):
        fixture = self.fixture(namespace=MISSING, local_pid=77)
        fixture.add_process(TARGET_PID, namespace=MISSING)
        with fixture.active():
            self.assert_unknown(fixture, fixture.load())

    def test_contradictory_target_status_pid_is_not_fallback(self):
        fixture = self.fixture(namespace=MISSING)
        fixture.add_process(TARGET_PID, namespace=MISSING, status_pid=TARGET_PID + 1)
        with fixture.active():
            self.assert_unknown(fixture, fixture.load())

    def test_contradictory_target_stat_pid_is_not_fallback(self):
        fixture = self.fixture(namespace=MISSING)
        fixture.add_process(TARGET_PID, namespace=MISSING, stat_pid=TARGET_PID + 1)
        with fixture.active():
            self.assert_unknown(fixture, fixture.load())

    def test_contradictory_target_nspid_is_not_fallback(self):
        fixture = self.fixture(namespace=MISSING)
        fixture.add_process(TARGET_PID, namespace=MISSING, nspid=[TARGET_PID + 1])
        with fixture.active():
            self.assert_unknown(fixture, fixture.load())

    def test_missing_target_stat_is_absent_but_permission_is_unknown(self):
        fixture = self.fixture(namespace=MISSING)
        fixture.add_process(TARGET_PID, namespace=MISSING)
        with fixture.active():
            scope = fixture.load()
            self.assertIsNone(scope.identity(TARGET_PID + 1))
            fixture.open_errors[f'/proc/{TARGET_PID}/stat'] = PermissionError(errno.EACCES, 'fixture denial')
            self.assert_unknown(fixture, scope)

    def test_unreadable_target_status_is_unknown_and_preserved(self):
        fixture = self.fixture(namespace=MISSING)
        fixture.add_process(TARGET_PID, namespace=MISSING)
        fixture.open_errors[f'/proc/{TARGET_PID}/status'] = PermissionError(errno.EACCES, 'fixture denial')
        with fixture.active():
            scope = fixture.load()
            self.assert_unknown(fixture, scope)
            pidfile, _ = self.register(fixture, legacy=True)
            self.assert_cancel_preserves(fixture, scope, pidfile)

    def test_live_target_with_missing_status_is_unknown(self):
        fixture = self.fixture(namespace=MISSING)
        fixture.add_process(TARGET_PID, namespace=MISSING)
        (fixture.proc / str(TARGET_PID) / 'status').unlink()
        with fixture.active():
            self.assert_unknown(fixture, fixture.load())

    def test_unknown_self_identity_preserves_legacy_owner_records(self):
        fixture = self.fixture(namespace=MISSING, self_nspid=MISSING)
        fixture.add_process(TARGET_PID, namespace=MISSING)
        pidfile, _ = self.register(fixture, legacy=True)
        with fixture.active():
            self.assert_cancel_preserves(fixture, fixture.load(), pidfile)

    def test_unknown_self_identity_preserves_structured_owner_records(self):
        fixture = self.fixture(namespace=MISSING, self_nspid=MISSING)
        fixture.add_process(TARGET_PID, namespace=MISSING)
        pidfile, _ = self.register(fixture)
        with fixture.active():
            self.assert_cancel_preserves(fixture, fixture.load(), pidfile)

    def test_unknown_identity_run_returns_structured_error_without_spawning(self):
        fixture = self.fixture(namespace=MISSING, self_nspid=MISSING)
        pidfile = fixture.module / 'config/new_worker.pid'
        with fixture.active():
            scope = fixture.load()
            code, messages, _ = self.invoke(scope, 'run', '--pid-file', pidfile,
                                           '--task', 'new-task', '--', 'fixture-command')
            self.assertEqual(code, 126)
            self.assertTrue(any(m.get('status') == 'error' and
                                m.get('data', {}).get('reason') == 'proc-identity-unavailable'
                                for m in messages), messages)
            self.assertFalse(pidfile.exists())
            self.assertFalse(Path(str(pidfile) + '.owner.json').exists())
            self.assertFalse(Path(str(pidfile) + '.ready').exists())

    def test_corrupt_kernel_config_is_unknown_without_import_crash(self):
        fixture = self.fixture(namespace=MISSING, self_nspid=MISSING)
        fixture.write('config.gz', b'\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\xff\xff\xff\xff\xff\x00')
        fixture.add_process(TARGET_PID, namespace=MISSING, nspid=MISSING)
        with fixture.active():
            self.assert_unknown(fixture, fixture.load())

    def test_conflicting_kernel_configuration_is_not_proof(self):
        fixture = self.fixture(namespace=MISSING, self_nspid=MISSING)
        fixture.configuration('# CONFIG_PID_NS is not set\nCONFIG_PID_NS=y\n')
        fixture.add_process(TARGET_PID, namespace=MISSING, nspid=MISSING)
        with fixture.active():
            self.assert_unknown(fixture, fixture.load())

    def test_non_procfs_view_is_not_fallback(self):
        fixture = self.fixture(namespace=MISSING)
        fixture.statfs_magic = 0xef53
        fixture.add_process(TARGET_PID, namespace=MISSING)
        with fixture.active():
            self.assert_unknown(fixture, fixture.load())

    def test_procfs_capability_change_after_init_is_unknown(self):
        fixture = self.fixture(namespace=MISSING)
        fixture.add_process(TARGET_PID, namespace=MISSING)
        with fixture.active():
            scope = fixture.load()
            record = scope.identity(TARGET_PID)
            fixture.statfs_magic = 0xef53
            self.assert_unknown(fixture, scope)
            pidfile, _ = self.register(fixture, record=record)
            self.assert_cancel_preserves(fixture, scope, pidfile)

    def test_target_missing_nspid_cannot_mix_with_single_nspid_mode(self):
        fixture = self.fixture(namespace=MISSING)
        fixture.configuration('# CONFIG_PID_NS is not set\n')
        fixture.add_process(TARGET_PID, namespace=MISSING, nspid=MISSING)
        with fixture.active():
            self.assert_unknown(fixture, fixture.load())

    def test_target_nspid_cannot_mix_with_disabled_namespace_mode(self):
        fixture = self.fixture(namespace=MISSING, self_nspid=MISSING)
        fixture.configuration('# CONFIG_PID_NS is not set\n')
        fixture.add_process(TARGET_PID, namespace=MISSING)
        with fixture.active():
            self.assert_unknown(fixture, fixture.load())

    def test_existing_process_with_missing_stat_is_unknown(self):
        fixture = self.fixture(namespace=MISSING)
        fixture.add_process(TARGET_PID, namespace=MISSING)
        (fixture.proc / str(TARGET_PID) / 'stat').unlink()
        with fixture.active():
            self.assert_unknown(fixture, fixture.load())

    def test_self_mapping_change_after_init_blocks_signaling(self):
        fixture = self.fixture(namespace=MISSING)
        fixture.add_process(TARGET_PID, namespace=MISSING)
        with fixture.active():
            scope = fixture.load()
            record = scope.identity(TARGET_PID)
            fixture.write(str(SELF_PID) + '/status', 'Pid: 4100\nTgid: 4100\nNSpid: 4100 77\n')
            with self.assertRaises(scope.IdentityUnavailable):
                scope.signal_record(record, signal.SIGTERM)

    def test_normal_signal_keeps_local_pid_mapping(self):
        fixture = self.fixture(self_nspid=[SELF_PID, 77], local_pid=77)
        fixture.add_process(TARGET_PID, nspid=[TARGET_PID, 88])
        with fixture.active():
            scope = fixture.load()
            record = scope.identity(TARGET_PID)
            with contextlib.ExitStack() as stack:
                kill = stack.enter_context(patch.object(os, 'kill'))
                if hasattr(os, 'pidfd_open'):
                    stack.enter_context(patch.object(os, 'pidfd_open', side_effect=OSError(errno.ENOSYS, 'fixture')))
                self.assertTrue(scope.signal_record(record, signal.SIGTERM))
                kill.assert_called_once_with(88, signal.SIGTERM)

    def test_pid_reuse_after_pidfd_open_blocks_signal(self):
        if not hasattr(os, 'pidfd_open') or not hasattr(signal, 'pidfd_send_signal'):
            self.skipTest('Python runtime does not expose pidfd APIs')
        fixture = self.fixture(namespace=MISSING)
        fixture.add_process(TARGET_PID, namespace=MISSING)
        with fixture.active():
            scope = fixture.load()
            record = scope.identity(TARGET_PID)
            def opened(pid):
                self.assertEqual(pid, TARGET_PID)
                fixture.write(str(TARGET_PID) + '/stat', stat_text(TARGET_PID, SELF_PID, '999'))
                return 888
            with patch.object(os, 'pidfd_open', side_effect=opened), patch.object(os, 'close') as close:
                self.assertFalse(scope.signal_record(record, signal.SIGTERM))
                close.assert_called_once_with(888)

    def test_fallback_owner_cancellation_uses_verified_identity(self):
        fixture = self.fixture(namespace=MISSING)
        fixture.add_process(TARGET_PID, namespace=MISSING)
        with fixture.active():
            scope = fixture.load()
            pidfile, owner = self.register(fixture, record=scope.identity(TARGET_PID))
            self.assertEqual(scope.read_owner(pidfile), owner)
            def terminated(pid, number):
                self.assertEqual((pid, number), (TARGET_PID, signal.SIGTERM))
                shutil.rmtree(fixture.proc / str(TARGET_PID))
                proof = dict(owner, schema='task-cleanup-v2', cleaned=True,
                             leftoverPids=[], cleanupErrors=[])
                Path(str(pidfile) + '.cleanup.json').write_text(json.dumps(proof))
            with contextlib.ExitStack() as stack:
                kill = stack.enter_context(patch.object(os, 'kill', side_effect=terminated))
                if hasattr(os, 'pidfd_open'):
                    stack.enter_context(patch.object(os, 'pidfd_open', side_effect=OSError(errno.ENOSYS, 'fixture')))
                code, messages, _ = self.invoke(scope, 'cancel', pidfile, owner['task'])
            self.assertEqual(code, 0)
            kill.assert_called_once_with(TARGET_PID, signal.SIGTERM)
            self.assertTrue(messages[-1]['data']['cleaned'])

    def test_fallback_legacy_cancellation_keeps_boot_command_start_checks(self):
        fixture = self.fixture(namespace=MISSING)
        fixture.add_process(TARGET_PID, namespace=MISSING)
        fixture.write(str(TARGET_PID) + '/cmdline', ('sh\0' + str(fixture.module / 'common/font_mix.sh') +
                      '\0worker\0fixture-task\0').encode())
        pidfile, _ = self.register(fixture, legacy=True)
        with fixture.active():
            scope = fixture.load()
            def terminated(pid, number):
                self.assertEqual((pid, number), (TARGET_PID, signal.SIGTERM))
                shutil.rmtree(fixture.proc / str(TARGET_PID))
            with contextlib.ExitStack() as stack:
                kill = stack.enter_context(patch.object(os, 'kill', side_effect=terminated))
                if hasattr(os, 'pidfd_open'):
                    stack.enter_context(patch.object(os, 'pidfd_open', side_effect=OSError(errno.ENOSYS, 'fixture')))
                code, messages, _ = self.invoke(scope, 'cancel-all', fixture.module)
            self.assertEqual(code, 0)
            kill.assert_called_once_with(TARGET_PID, signal.SIGTERM)
            self.assertFalse(pidfile.exists())
            self.assertTrue(messages[-1]['data']['cleaned'])

    def test_fallback_legacy_reused_pid_preserves_records(self):
        fixture = self.fixture(namespace=MISSING)
        fixture.add_process(TARGET_PID, namespace=MISSING, start='999')
        fixture.write(str(TARGET_PID) + '/cmdline', b'sleep\0' + b'600\0')
        pidfile, _ = self.register(fixture, legacy=True)
        with fixture.active():
            self.assert_cancel_preserves(fixture, fixture.load(), pidfile)

    def test_old_namespace_cleanup_proof_cannot_clear_fallback_owner(self):
        fixture = self.fixture(namespace=MISSING)
        fixture.add_process(TARGET_PID, namespace=MISSING)
        pidfile, owner = self.register(fixture)
        proof = dict(owner, schema='task-cleanup-v2', cleaned=True, leftoverPids=[], cleanupErrors=[])
        Path(str(pidfile) + '.cleanup.json').write_text(json.dumps(proof))
        with fixture.active():
            self.assert_cancel_preserves(fixture, fixture.load(), pidfile)

    def test_malformed_saved_boot_cannot_retire_unknown_owner(self):
        fixture = self.fixture(namespace=MISSING, self_nspid=MISSING)
        fixture.add_process(TARGET_PID, namespace=MISSING)
        with fixture.active():
            scope = fixture.load()
            for boot in ('unknown', 'previous-boot', '1785281995000', '', 'not-a-uuid'):
                with self.subTest(boot=boot):
                    record = dict(procPid=TARGET_PID, pid=TARGET_PID, parent=SELF_PID,
                                  state='S', start='200', namespace=NS, boot=boot)
                    pidfile, _ = self.register(fixture, record=record)
                    self.assert_cancel_preserves(fixture, scope, pidfile)

    def test_malformed_saved_boot_cannot_retire_legacy_sidecars(self):
        fixture = self.fixture(namespace=MISSING, self_nspid=MISSING)
        fixture.add_process(TARGET_PID, namespace=MISSING)
        with fixture.active():
            scope = fixture.load()
            for boot in ('unknown', 'previous-boot', '1785281995000', '', 'not-a-uuid'):
                with self.subTest(boot=boot):
                    record = dict(procPid=TARGET_PID, pid=TARGET_PID, parent=SELF_PID,
                                  state='S', start='200', namespace=NS, boot=boot)
                    pidfile, _ = self.register(fixture, record=record, legacy=True)
                    self.assert_cancel_preserves(fixture, scope, pidfile)

    def test_valid_previous_boot_can_retire_owner_without_namespace(self):
        fixture = self.fixture(namespace=MISSING, self_nspid=MISSING)
        record = dict(procPid=TARGET_PID, pid=TARGET_PID, parent=SELF_PID,
                      state='S', start='200', namespace=NS, boot=OLD_BOOT)
        pidfile, _ = self.register(fixture, record=record)
        with fixture.active():
            code, messages, _ = self.invoke(fixture.load(), 'cancel-all', fixture.module)
        self.assertEqual(code, 0)
        self.assertFalse(pidfile.exists())
        self.assertEqual(messages[-1]['data']['state'], 'previous-boot')

    def test_unreadable_task_root_is_not_an_empty_cancellation(self):
        fixture = self.fixture(namespace=MISSING, self_nspid=MISSING)
        root = fixture.module / 'config'
        root.mkdir()
        (root / 'untouched').write_text('evidence')
        before = self.snapshot(fixture)
        fixture.stat_errors[str(root)] = PermissionError(errno.EACCES, 'fixture root denial')
        with fixture.active():
            code, messages, _ = self.invoke(fixture.load(), 'cancel-all', fixture.module)
        self.assertEqual(code, 126)
        self.assertEqual(self.snapshot(fixture), before)
        self.assertTrue(any(m.get('status') == 'error' for m in messages))

    def test_unreadable_owner_subdirectory_is_not_empty(self):
        fixture = self.fixture(namespace=MISSING, self_nspid=MISSING)
        root = fixture.module / 'config/locked'
        root.mkdir(parents=True)
        (root / 'saved.owner.json').write_text('unreadable ownership evidence')
        before = self.snapshot(fixture)
        fixture.scandir_errors[str(root)] = PermissionError(errno.EACCES, 'fixture owner scan denial')
        with fixture.active():
            code, messages, _ = self.invoke(fixture.load(), 'cancel-all', fixture.module)
        self.assertEqual(code, 126)
        self.assertEqual(self.snapshot(fixture), before)
        self.assertTrue(any(m.get('status') == 'error' for m in messages))

    def test_unreadable_legacy_enumeration_is_not_empty(self):
        fixture = self.fixture(namespace=MISSING, self_nspid=MISSING)
        root = fixture.module / 'config'
        root.mkdir()
        (root / 'mix_worker.pid').write_text(str(TARGET_PID))
        before = self.snapshot(fixture)
        fixture.iterdir_errors[str(root)] = PermissionError(errno.EACCES, 'fixture legacy scan denial')
        with fixture.active():
            code, messages, _ = self.invoke(fixture.load(), 'cancel-all', fixture.module)
        self.assertEqual(code, 126)
        self.assertEqual(self.snapshot(fixture), before)
        self.assertTrue(any(m.get('status') == 'error' for m in messages))

    def test_unknown_namespace_cannot_accept_current_boot_cleanup_proof(self):
        fixture = self.fixture(namespace=MISSING, self_nspid=MISSING)
        pidfile = fixture.module / 'config/proof_only.pid'
        pidfile.parent.mkdir()
        with fixture.active():
            scope = fixture.load()
            for namespace in (MISSING, None):
                for action, expected_code in (('cancel', 125), ('cleaned', 1), ('settled', 125)):
                    with self.subTest(namespace=namespace, action=action):
                        proof = dict(schema='task-cleanup-v2', task='fixture-task', pid=TARGET_PID,
                                     start='200', boot=BOOT, cleaned=True, leftoverPids=[], cleanupErrors=[])
                        if namespace is not MISSING:
                            proof['namespace'] = namespace
                        Path(str(pidfile) + '.cleanup.json').write_text(json.dumps(proof))
                        before = self.snapshot(fixture)
                        code, _, _ = self.invoke(scope, action, pidfile, 'fixture-task')
                        self.assertEqual(code, expected_code)
                        self.assertEqual(self.snapshot(fixture), before)

    def test_known_namespace_also_requires_explicit_proof_namespace(self):
        fixture = self.fixture()
        pidfile = fixture.module / 'config/proof_only.pid'
        pidfile.parent.mkdir()
        with fixture.active():
            scope = fixture.load()
            for namespace in (MISSING, None):
                for action, expected_code in (('cancel', 125), ('cleaned', 1), ('settled', 125)):
                    with self.subTest(namespace=namespace, action=action):
                        proof = dict(schema='task-cleanup-v2', task='fixture-task', pid=TARGET_PID,
                                     start='200', boot=BOOT, cleaned=True, leftoverPids=[], cleanupErrors=[])
                        if namespace is not MISSING:
                            proof['namespace'] = namespace
                        Path(str(pidfile) + '.cleanup.json').write_text(json.dumps(proof))
                        before = self.snapshot(fixture)
                        code, _, _ = self.invoke(scope, action, pidfile, 'fixture-task')
                        self.assertEqual(code, expected_code)
                        self.assertEqual(self.snapshot(fixture), before)

    def test_hidden_live_local_pid_preserves_legacy_records(self):
        fixture = self.fixture(namespace=MISSING)
        pidfile, _ = self.register(fixture, legacy=True)
        with fixture.active():
            scope = fixture.load()
            def probe(pid, number):
                self.assertEqual((pid, number), (TARGET_PID, 0), 'only exact non-signalling existence probes are allowed')
            with patch.object(os, 'kill', side_effect=probe) as kill:
                self.assert_cancel_preserves(fixture, scope, pidfile)
                kill.assert_called_once_with(TARGET_PID, 0)

    def test_hidden_local_pid_permission_denial_preserves_legacy_records(self):
        fixture = self.fixture(namespace=MISSING)
        pidfile, _ = self.register(fixture, legacy=True)
        with fixture.active():
            scope = fixture.load()
            def probe(pid, number):
                self.assertEqual((pid, number), (TARGET_PID, 0), 'only exact non-signalling existence probes are allowed')
                raise PermissionError(errno.EPERM, 'fixture hidden live PID')
            with patch.object(os, 'kill', side_effect=probe) as kill:
                self.assert_cancel_preserves(fixture, scope, pidfile)
                kill.assert_called_once_with(TARGET_PID, 0)

    def test_confirmed_absent_proc_and_local_pid_can_retire_legacy_records(self):
        fixture = self.fixture(namespace=MISSING)
        pidfile, _ = self.register(fixture, legacy=True)
        sentinel = pidfile.parent / 'unrelated-record'
        sentinel.write_text('untouched')
        with fixture.active():
            scope = fixture.load()
            def probe(pid, number):
                self.assertEqual((pid, number), (TARGET_PID, 0), 'only exact non-signalling existence probes are allowed')
                raise ProcessLookupError(errno.ESRCH, 'fixture absent PID')
            with patch.object(os, 'kill', side_effect=probe) as kill:
                code, _, _ = self.invoke(scope, 'cancel-all', fixture.module)
                kill.assert_called_once_with(TARGET_PID, 0)
        self.assertEqual(code, 0)
        for suffix in ('', '.task', '.start', '.boot'):
            self.assertFalse(Path(str(pidfile) + suffix).exists())
        self.assertEqual(sentinel.read_text(), 'untouched')

    def test_inconclusive_local_pid_probe_preserves_legacy_records(self):
        fixture = self.fixture(namespace=MISSING)
        pidfile, _ = self.register(fixture, legacy=True)
        with fixture.active():
            scope = fixture.load()
            def probe(pid, number):
                self.assertEqual((pid, number), (TARGET_PID, 0), 'only exact non-signalling existence probes are allowed')
                raise OSError(errno.EINVAL, 'fixture inconclusive probe')
            with patch.object(os, 'kill', side_effect=probe) as kill:
                self.assert_cancel_preserves(fixture, scope, pidfile)
                kill.assert_called_once_with(TARGET_PID, 0)

    def test_existing_other_namespace_proc_is_not_proven_absent(self):
        fixture = self.fixture()
        fixture.add_process(TARGET_PID, namespace='pid:[different]')
        pidfile, _ = self.register(fixture, legacy=True)
        with fixture.active():
            # The default os.kill guard also proves no signal-zero probe can
            # replace the required proc-view identity check.
            self.assert_cancel_preserves(fixture, fixture.load(), pidfile)

    def test_valid_previous_boot_retires_legacy_without_process_capability(self):
        fixture = self.fixture(namespace=MISSING, self_nspid=MISSING)
        record = dict(procPid=TARGET_PID, pid=TARGET_PID, parent=SELF_PID,
                      state='S', start='200', namespace=NS, boot=OLD_BOOT)
        pidfile, _ = self.register(fixture, record=record, legacy=True)
        fixture.iterdir_errors['/proc'] = AssertionError('previous boot must not enumerate live processes')
        with fixture.active():
            code, _, _ = self.invoke(fixture.load(), 'cancel-all', fixture.module)
        self.assertEqual(code, 0)
        for suffix in ('', '.task', '.start', '.boot'):
            self.assertFalse(Path(str(pidfile) + suffix).exists())

    def test_oversized_kernel_configuration_is_not_prefix_only_proof(self):
        fixture = self.fixture(namespace=MISSING, self_nspid=MISSING)
        fixture.configuration('# CONFIG_PID_NS is not set\n' + '# filler\n' * 250000 + 'CONFIG_PID_NS=y\n')
        fixture.add_process(TARGET_PID, namespace=MISSING, nspid=MISSING)
        with fixture.active():
            self.assert_unknown(fixture, fixture.load())

    def test_normal_missing_target_namespace_is_unknown_not_absent(self):
        fixture = self.fixture()
        fixture.add_process(TARGET_PID, namespace=MISSING)
        with fixture.active():
            self.assert_unknown(fixture, fixture.load())


if __name__ == '__main__':
    unittest.main()
