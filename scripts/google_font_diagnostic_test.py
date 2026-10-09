#!/usr/bin/env python3
"""Host-only, read-only diagnostic fixtures. No OnePlus rendering claim."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'common'))
SPEC = importlib.util.spec_from_file_location('google_diagnostic', ROOT / 'common/google_font_diagnostic.py')
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def package_dump(user=0, component_state=2, version=123, code='/data/app/private-install-token/base'):
    text = ('Registered ContentProviders:\n'
            '  com.google.android.gms/.fonts.provider.FontsProvider:\n'
            '    Provider{abc com.google.android.gms/com.google.android.gms.fonts.provider.FontsProvider}\n'
            'Packages:\n  Package [com.google.android.gms] (abc):\n'
            f'    userId=10123\n    versionCode={version} minSdk=28 targetSdk=36\n'
            f'    lastUpdateTime=2026-10-07 12:00:00\n    codePath={code}\n'
            f'    User {user}: installed=true enabled=0\n'
            '      firstInstallTime=2026-01-01 12:00:00\n')
    if component_state:
        text += ('      ' + ('disabled' if component_state == 2 else 'enabled') + 'Components:\n'
                 '        com.google.android.gms.fonts.provider.FontsProvider\n')
    return text


def filesystem_snapshot(root):
    result = {}
    for path in root.rglob('*'):
        s = path.lstat()
        relative = str(path.relative_to(root))
        content = os.readlink(path) if path.is_symlink() else path.read_bytes() if path.is_file() else None
        result[relative] = (s.st_mode, s.st_uid, s.st_ino, s.st_mtime_ns, content)
    return result


class GoogleDiagnosticTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='luoshu-google-diagnostic-fixture-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.module = self.root / 'data/adb/modules/LuoShu'
        (self.module / 'config').mkdir(parents=True)
        (self.module / 'module.prop').write_text('id=LuoShu\nversion=v2.2.2\nversionCode=70202\n')
        self.config('active_font.conf', 'Private User Font\n')
        self.user = 0
        self.state = 2
        self.commands = []
        self.pids = [101]
        self.dump_count = 0
        self.boot = '00000000-0000-4000-8000-000000000000'
        self.write('/proc/sys/kernel/random/boot_id', self.boot)
        self.write('/data/fonts/config/config.xml', '<config version="2"><family name="Private User Font"/></config>')
        self.write('/system/fonts/GoogleSansText-Regular.ttf', b'system-font-content-do-not-export')
        self.write('/system/fonts/PrivateUserFont.ttf', b'private-font-content-do-not-read')
        self.write('/data/user/0/com.google.android.gms/files/fonts/opaque-private-cache-key', b'font-bytes-never-read')
        self.target = '/data/user/0/com.google.android.gms/files/fonts/opaque-private-cache-key'
        self.old = self.path(self.target)
        self.old_stat = self.old.stat()
        self.old_id = f'{self.old_stat.st_dev}:{self.old_stat.st_ino}'
        self.clone = self.module / '.luoshu-state/cache/google-font-provider' / ('a' * 64 + '.ttf')
        self.clone.parent.mkdir(parents=True)
        self.clone.write_bytes(b'clone-content-never-read')
        self.config('google-font-provider-mounts.conf', f'{self.target}|{self.clone}|oldhash|clonehash|sourcehash|400|provider-v3|{self.old_id}\n')
        cs = self.clone.stat()
        self.config('google-font-provider-namespaces.conf', f'mnt:[900]|{self.target}|{cs.st_dev}:{cs.st_ino}:{cs.st_size}|{self.clone}\n')
        self.config('google-font-refresh-pending.conf', f'101|100|com.android.vending|0|{self.old_id}|0|{os.major(self.old_stat.st_dev):x}:{os.minor(self.old_stat.st_dev):x}:{self.old_stat.st_ino}\n')
        self.config('google-font-refresh-pending.conf.boot', self.boot)
        self.config('device-font-load-verification.conf', 'state=verified\nmode=mount-confirmed\ntime=1\nactiveFont=Private User Font\n')
        self.saved = dict(m.parse_snapshot(package_dump(component_state=0), 0), schema=m.UNDO_SCHEMA, original=0,
                          lastVerifiedVersionCode=122, lastVerifiedUpdateTime='2026-10-06 12:00:00',
                          lastVerifiedCodePath='/data/app/older-private-path/base')
        self.save_journal()
        self.process()

    def path(self, absolute):
        return self.root / absolute.lstrip('/')

    def write(self, absolute, text):
        path = self.path(absolute)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text if isinstance(text, bytes) else text.encode())
        return path

    def config(self, name, text):
        (self.module / 'config' / name).write_text(text)

    def save_journal(self):
        folder = self.path('/data/adb/luoshu/google-font-fallback')
        folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = folder / f'user-{self.user}.json'
        path.write_text(json.dumps(self.saved))
        path.chmod(0o600)

    def process(self, pid=101, name='com.android.vending', uid=10123, start=100):
        p = self.path(f'/proc/{pid}')
        (p / 'fd').mkdir(parents=True, exist_ok=True)
        (p / 'ns').mkdir(exist_ok=True)
        (p / 'cmdline').write_bytes(name.encode() + b'\0private-argument-do-not-export\0')
        (p / 'status').write_text(f'Uid:\t{uid}\t{uid}\t{uid}\t{uid}\n')
        (p / 'stat').write_text(f'{pid} (font process) S ' + '0 ' * 18 + str(start) + ' 0\n')
        (p / 'maps').write_text(f'0000-1000 r--p 00000000 {os.major(self.old_stat.st_dev):02x}:{os.minor(self.old_stat.st_dev):02x} {self.old_stat.st_ino} /private-map-path-secret (deleted)\n')
        (p / 'mountinfo').write_text(f'1 0 0:1 / {self.target} ro - ext4 /private-source-secret ro\n')
        for name, destination in [('ns/mnt', 'mnt:[900]'), ('fd/7', str(self.old)), ('root', str(self.root))]:
            link = p / name
            link.unlink(missing_ok=True)
            link.symlink_to(destination)
        return p

    def runner(self, args):
        self.commands.append(args)
        if args == ('/system/bin/dumpsys', '-t', '1', 'package', m.GMS):
            self.dump_count += 1
            return package_dump(self.user, self.state), 'read'
        if args[0] == '/system/bin/pidof':
            self.assertEqual(args[1:], (*m.PACKAGES, *m.SYSTEM_PROCESSES))
            return ' '.join(str(p) for p in self.pids), 'read'
        if args == ('/system/bin/cmd', 'font', 'dump'):
            return 'configVersion=9\nFamily google-sans-text Private User Font /private/font/path\nFamily oplus-sans\n', 'read'
        if args[0] == '/system/bin/getprop':
            self.assertIn(args[1], m.PROPERTIES)
            return '36' if args[1] == 'ro.build.version.sdk' else 'OnePlus-Fixture', 'read'
        self.fail('unexpected Android command: ' + repr(args))

    def collector(self, **kwargs):
        return m.Collector(self.module, self.user, 'before-maintenance', root=self.root,
                           runner=self.runner, **kwargs)

    def collect(self, **kwargs):
        return self.collector(**kwargs).collect()

    def test_disabled_owned_component_and_exact_old_fd_mmap_are_distinct_evidence(self):
        result = self.collect()
        self.assertEqual(result['user'], 0)
        self.assertEqual(result['phase'], 'before-maintenance')
        self.assertEqual(result['component']['classification'], 'managed-disabled')
        self.assertEqual(result['component']['actual']['componentState'], 2)
        self.assertEqual(result['component']['stability'], 'stable')
        self.assertEqual(result['component']['verifiedRevision']['versionCode'], 122)
        evidence = result['provider']['processes'][0]['oldDescriptorEvidence']
        self.assertEqual((evidence['fdMatches'], evidence['mmapMatches']), (1, 1))
        self.assertEqual(evidence['memoryTypefaceCache'], 'unknown')
        self.assertFalse(result['provider']['processes'][0]['targetViews'][0]['ownedMountMatches'])
        self.assertTrue(result['provider']['processes'][0]['targetViews'][0]['mountPresent'])
        self.assertTrue(result['provider']['processes'][0]['targetViews'][0]['mountReadonly'])

    def test_enabled_or_default_actual_state_is_not_reported_as_disabled(self):
        for state in (0, 1):
            with self.subTest(state=state):
                self.state = state
                result = self.collect()
                self.assertEqual(result['component']['actual']['componentState'], state)
                self.assertEqual(result['component']['classification'], 'managed-component-changed')

    def test_non_owner_user_is_exact_and_has_no_owner_user_journal_or_process_evidence(self):
        self.user = 12
        self.saved['user'] = 12
        self.save_journal()
        result = self.collect()
        self.assertEqual(result['user'], 12)
        self.assertEqual(result['component']['undo']['user'], 12)
        self.assertTrue(result['component']['managed'])
        self.assertEqual(result['provider']['processes'], [])
        self.assertEqual(result['provider']['pending'], [])
        self.assertEqual(result['provider']['targets'], [])

    def test_capture_is_completely_nonmutating_and_never_reads_provider_font_contents(self):
        before = filesystem_snapshot(self.root)
        real_open = Path.open
        def guarded_open(path, *args, **kwargs):
            mode = args[0] if args else kwargs.get('mode', 'r')
            self.assertFalse(any(x in mode for x in 'wax+'), str(path))
            self.assertNotIn('opaque-private-cache-key', str(path))
            self.assertNotEqual(path, self.clone)
            self.assertNotEqual(path.name, 'PrivateUserFont.ttf')
            return real_open(path, *args, **kwargs)
        with patch.object(Path, 'open', guarded_open), \
             patch.object(os, 'chmod', side_effect=AssertionError('chmod')), \
             patch.object(os, 'rename', side_effect=AssertionError('rename')), \
             patch.object(os, 'replace', side_effect=AssertionError('replace')), \
             patch.object(os, 'unlink', side_effect=AssertionError('unlink')), \
             patch.object(os, 'mkdir', side_effect=AssertionError('mkdir')):
            result = self.collect()
        self.assertEqual(filesystem_snapshot(self.root), before)
        self.assertTrue(result['component']['managed'])
        self.assertTrue(all(command[0] in ('/system/bin/dumpsys', '/system/bin/cmd', '/system/bin/pidof', '/system/bin/getprop') for command in self.commands))
        self.assertFalse(any('pm' in command or 'kill' in command or 'apply' in command or 'refresh' in command for command in self.commands))

    def test_paths_names_arguments_and_map_body_are_redacted(self):
        raw = m.encode(self.collect())
        for secret in ('opaque-private-cache-key', 'private-install-token', 'older-private-path',
                       'Private User Font', 'private-argument-do-not-export', 'private-map-path-secret',
                       'font-bytes-never-read', 'clone-content-never-read', '/private/font/path'):
            self.assertNotIn(secret, raw)
        self.assertIn('google-sans-text', raw)
        self.assertIn('oplus-sans', raw)
        self.assertLessEqual(len(raw.encode()), m.MAX_JSON_BYTES)

    def test_new_provider_candidate_is_metadata_only_and_not_claimed_as_font(self):
        new = self.write('/data/user/0/com.android.vending/files/fonts/new-private-opaque-file', b'arbitrary-cache-not-a-font')
        result = self.collect()
        candidate = next(t for t in result['provider']['targets'] if t['pathToken'] == m.token('/' + str(new.relative_to(self.root))))
        self.assertFalse(candidate['recorded'])
        self.assertEqual(candidate['recognition'], 'unknown-metadata-only')
        self.assertEqual(result['provider']['unrecordedCandidates'], 1)
        self.assertNotIn('arbitrary-cache-not-a-font', m.encode(result))

    def test_provider_directory_link_cannot_scan_another_apps_directory(self):
        folder = self.path('/data/user/0/com.android.vending/files/fonts')
        folder.parent.mkdir(parents=True, exist_ok=True)
        foreign = self.write('/data/user/0/com.private.unrelated/files/foreign-secret', 'never-read').parent
        folder.symlink_to(foreign)
        result = self.collect()
        self.assertIn('provider-directory-outside-allowlist', result['collection']['reasons'])
        self.assertNotIn(m.token('/data/user/0/com.private.unrelated/files/foreign-secret'), m.encode(result))

    def test_other_android_user_files_processes_and_pending_are_not_read(self):
        self.write('/data/user/10/com.google.android.gms/files/fonts/other-user-secret', 'do-not-read')
        p = self.process(102, uid=1010123)
        self.pids.append(102)
        self.config('google-font-refresh-pending.conf', (self.module / 'config/google-font-refresh-pending.conf').read_text() +
                    f'102|100|com.android.vending|10|{self.old_id}|0|0:0:1\n')
        real_read = m.Collector.read
        def guarded_read(collector, path, *args, **kwargs):
            self.assertNotIn('/data/user/10/', str(path))
            self.assertFalse(str(path).startswith(str(p / 'maps')))
            self.assertFalse(str(path).startswith(str(p / 'fd')))
            return real_read(collector, path, *args, **kwargs)
        with patch.object(m.Collector, 'read', guarded_read):
            result = self.collect()
        self.assertEqual([p['pid'] for p in result['provider']['processes']], [101])
        self.assertEqual([q['pid'] for q in result['provider']['pending']], [101])
        self.assertNotIn('other-user-secret', m.encode(result))

    def test_non_allowlisted_pid_reuse_does_not_read_status_maps_or_fds(self):
        p = self.process(102, name='com.private.unrelated')
        self.pids.append(102)
        (p / 'status').unlink()
        (p / 'maps').unlink()
        result = self.collect()
        self.assertEqual([p['pid'] for p in result['provider']['processes']], [101])
        self.assertIn('process-identity-changed', result['collection']['reasons'])

    def test_inaccessible_proc_is_unknown_instead_of_zero_matches(self):
        p = self.path('/proc/101')
        (p / 'fd/7').unlink()
        (p / 'fd').rmdir()
        (p / 'maps').unlink()
        result = self.collect()
        evidence = result['provider']['processes'][0]['oldDescriptorEvidence']
        self.assertEqual(evidence['fdReadState'], 'unavailable')
        self.assertIsNone(evidence['fdMatches'])
        self.assertIsNone(evidence['mmapMatches'])
        self.assertFalse(result['collection']['complete'])

    def test_process_exit_or_reuse_after_sampling_invalidates_all_old_fd_claims(self):
        collector = self.collector()
        real_start = collector.process_start
        calls = 0
        def changing_start(pid):
            nonlocal calls
            calls += 1
            return real_start(pid) if calls == 1 else 999
        collector.process_start = changing_start
        result = collector.collect()
        process = result['provider']['processes'][0]
        self.assertEqual(process['readState'], 'unknown-process-changed-during-collection')
        self.assertNotIn('oldDescriptorEvidence', process)

    def test_fd_and_maps_limits_are_explicit_and_keep_output_bounded(self):
        p = self.path('/proc/101')
        for fd in range(300, 300 + m.MAX_FDS + 1):
            (p / 'fd' / str(fd)).symlink_to(self.old)
        (p / 'maps').write_text('x' * (m.MAX_MAP_BYTES + 1))
        result = self.collect()
        evidence = result['provider']['processes'][0]['oldDescriptorEvidence']
        self.assertEqual(evidence['fdReadState'], 'truncated')
        self.assertEqual(evidence['mapsReadState'], 'truncated')
        self.assertIsNone(evidence['fdMatches'])
        self.assertTrue(result['collection']['truncated'])
        self.assertLessEqual(len(m.encode(result).encode()), m.MAX_JSON_BYTES)

    def test_time_budget_returns_partial_evidence(self):
        result = self.collect(budget_ms=0)
        self.assertTrue(result['collection']['truncated'])
        self.assertIn('time-budget-exhausted', result['collection']['reasons'])
        self.assertEqual(result['component']['classification'], 'unknown')

    def test_component_revision_or_state_changes_during_capture_are_visible(self):
        original = self.runner
        def race(args):
            response = original(args)
            if args == ('/system/bin/dumpsys', '-t', '1', 'package', m.GMS) and self.dump_count == 2:
                return package_dump(0, 0, version=124), 'read'
            return response
        collector = self.collector()
        collector.runner = race
        result = collector.collect()
        self.assertEqual(result['component']['actual']['componentState'], 2)
        self.assertEqual(result['component']['afterCollection']['actual']['componentState'], 0)
        self.assertEqual(result['component']['stability'], 'changed-during-collection')

    def test_component_package_after_large_provider_dump_is_still_readable(self):
        original = self.runner
        def large(args):
            text, state = original(args)
            if args == ('/system/bin/dumpsys', '-t', '1', 'package', m.GMS):
                text = text.replace('Packages:\n', ('  Private provider detail secret\n' * 10000) + 'Packages:\n')
            return text, state
        collector = self.collector()
        collector.runner = large
        result = collector.collect()
        self.assertEqual(result['component']['actual']['componentState'], 2)
        self.assertEqual(result['component']['stability'], 'stable')
        self.assertNotIn('Private provider detail secret', m.encode(result))

    def test_stale_boot_pending_pids_are_not_observed_as_current_cached_descriptors(self):
        self.config('google-font-refresh-pending.conf.boot', '11111111-1111-4111-8111-111111111111')
        self.pids = []
        result = self.collect()
        self.assertFalse(result['provider']['pendingSameBoot'])
        self.assertEqual(result['provider']['stalePendingCount'], 1)
        self.assertEqual(result['provider']['processes'], [])

    def test_unsafe_or_foreign_journal_is_not_repaired(self):
        folder = self.path('/data/adb/luoshu/google-font-fallback')
        folder.chmod(0o777)
        before = filesystem_snapshot(self.root)
        result = self.collect()
        self.assertEqual(result['component']['undo']['readState'], 'unsafe-directory')
        self.assertFalse(result['component']['managed'])
        self.assertEqual(filesystem_snapshot(self.root), before)

    def test_unowned_automatic_preflight_uses_no_android_commands_or_proc_access(self):
        journal = self.path('/data/adb/luoshu/google-font-fallback/user-0.json')
        real_path = m.Collector.path
        for mode in ('missing', 'unsafe', 'invalid'):
            with self.subTest(mode=mode):
                self.save_journal()
                if mode == 'missing':
                    journal.unlink()
                elif mode == 'unsafe':
                    journal.chmod(0o666)
                else:
                    journal.write_text('{"schema":"foreign-tool-record"}')
                before = filesystem_snapshot(self.root)
                def no_proc_path(collector, absolute):
                    self.assertFalse(absolute.startswith('/proc/'), absolute)
                    return real_path(collector, absolute)
                collector = self.collector()
                collector.runner = lambda args: self.fail('unowned preflight must not execute Android commands')
                with patch.object(m.Collector, 'path', no_proc_path), \
                     patch.object(os, 'scandir', side_effect=AssertionError('unowned preflight directory scan')):
                    result = collector.collect()
                self.assertEqual(result['user'], 0)
                self.assertEqual(result['schema'], m.SCHEMA)
                self.assertEqual(result['phase'], 'before-maintenance')
                self.assertEqual(result['component']['classification'], 'not-owned')
                self.assertIsNone(result['component']['actual'])
                self.assertFalse(result['component']['managed'])
                self.assertEqual(result['collection']['scope'], 'ownership-only')
                self.assertEqual(result['collection']['skippedReason'], 'no-validated-owned-undo')
                self.assertEqual(filesystem_snapshot(self.root), before)

    def test_old_v1_owned_undo_still_collects_full_evidence(self):
        self.saved.pop('lastVerifiedVersionCode')
        self.saved.pop('lastVerifiedUpdateTime')
        self.saved.pop('lastVerifiedCodePath')
        self.save_journal()
        result = self.collect()
        self.assertTrue(self.commands)
        self.assertEqual(result['component']['classification'], 'managed-disabled')
        self.assertEqual(result['component']['verifiedRevision']['versionCode'], 123)
        self.assertEqual(result['collection']['scope'], 'full-evidence')

    def test_explicit_report_without_owned_record_still_collects_android_evidence(self):
        self.path('/data/adb/luoshu/google-font-fallback/user-0.json').unlink()
        collector = self.collector()
        collector.phase = 'explicit-report'
        collector.report['phase'] = 'explicit-report'
        result = collector.collect()
        self.assertTrue(self.commands)
        self.assertEqual(result['component']['actual']['componentState'], 2)
        self.assertEqual(result['component']['classification'], 'unmanaged-disabled')
        self.assertEqual(result['collection']['scope'], 'full-evidence')

    def test_historical_verified_does_not_claim_live_device_rendering(self):
        result = self.collect()
        history = result['systemFonts']['historicalVerification']
        self.assertEqual(history['state'], 'verified')
        self.assertEqual(history['time'], 1)
        self.assertIs(history['currentRenderingProven'], False)
        self.assertTrue(result['module']['activeCustomFont'])
        self.assertEqual(result['module']['versionCode'], 70202)

    def test_output_limit_removes_large_views_with_explicit_truncation(self):
        result = self.collect()
        process = result['provider']['processes'][0]
        process['targetViews'] = [{'targetToken': 'x' * 1000}] * 100
        raw = m.encode(result)
        self.assertLessEqual(len(raw.encode()), m.MAX_JSON_BYTES)
        parsed = json.loads(raw)
        self.assertIn('output-byte-limit', parsed['collection']['reasons'])
        self.assertNotIn('targetViews', parsed['provider']['processes'][0])

    def test_final_output_limit_has_a_fixed_envelope_for_future_unbounded_fields(self):
        result = self.collect()
        result['provider']['processes'][0]['futureField'] = 'x' * 150000
        result['systemFonts']['futureField'] = 'y' * 100000
        raw = m.encode(result)
        self.assertLessEqual(len(raw.encode()), m.MAX_JSON_BYTES)
        parsed = json.loads(raw)
        self.assertEqual(parsed['schema'], m.SCHEMA)
        self.assertEqual(parsed['user'], 0)
        self.assertEqual(parsed['phase'], 'before-maintenance')
        self.assertEqual(parsed['component']['actual']['componentState'], 2)
        self.assertTrue(parsed['collection']['truncated'])
        self.assertIn('output-byte-limit', parsed['collection']['reasons'])

    def test_cli_has_no_output_or_external_path_argument_and_validates_phase_user(self):
        for args in (['--user', '-1', '--phase', 'explicit-report'],
                     ['--user', '0', '--phase', 'unknown'],
                     ['--user', '0', '--phase', 'explicit-report', '--output', '/data/private']):
            result = subprocess.run([sys.executable, str(ROOT / 'common/google_font_diagnostic.py'), *args],
                                    capture_output=True, timeout=3)
            self.assertEqual(result.returncode, 2)

    def test_subprocess_read_is_bounded_by_bytes_and_deadline(self):
        collector = m.Collector(self.module, 0, 'explicit-report')
        text, state = collector.command((sys.executable, '-c', 'print("x" * 100000)'), limit=128)
        self.assertEqual(len(text.encode()), 128)
        self.assertEqual(state, 'truncated')
        start = time.monotonic()
        text, state = collector.command((sys.executable, '-c', 'import time; time.sleep(10)'), seconds=.05)
        self.assertEqual(state, 'timeout')
        self.assertLess(time.monotonic() - start, 1)

    def test_cli_alarm_interrupts_a_blocking_read_and_still_emits_valid_partial_json(self):
        # Scale only the test's clock constant. The public CLI has no override,
        # and production remains fixed at 8,000 ms.
        code = f'''import importlib.util, sys, time
from pathlib import Path
sys.path.insert(0, {str(ROOT / 'common')!r})
spec = importlib.util.spec_from_file_location('diagnostic_alarm_fixture', {str(ROOT / 'common/google_font_diagnostic.py')!r})
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
m.BUDGET_MS = 100
Original = m.Collector
class Blocking(Original):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.runner = self.slow_read
    def slow_read(self, args):
        time.sleep(10)
        return '', 'unavailable'
m.Collector = Blocking
sys.argv = ['google_font_diagnostic.py', '--user', '0', '--phase', 'explicit-report']
raise SystemExit(m.main())
'''
        start = time.monotonic()
        result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=3,
                                env={**os.environ, 'MODDIR': str(self.module)})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLess(time.monotonic() - start, 2)
        parsed = json.loads(result.stdout)
        self.assertEqual(parsed['user'], 0)
        self.assertEqual(parsed['phase'], 'explicit-report')
        self.assertIn('time-budget-exhausted', parsed['collection']['reasons'])
        self.assertTrue(parsed['collection']['truncated'])

    def test_manifest_and_aggregate_gate_include_new_collector(self):
        manifest = (ROOT / 'scripts/module_payload_manifest.txt').read_text().splitlines()
        for name in ('common/google_font_diagnostic.py', 'common/google_font_diagnostic.sh'):
            self.assertIn(name, manifest)
        self.assertIn('google_font_diagnostic_test.py', (ROOT / 'scripts/check.sh').read_text())


if __name__ == '__main__':
    unittest.main(verbosity=2)
