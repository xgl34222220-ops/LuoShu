#!/usr/bin/env python3
"""Real boot callers and finite stock-scan supervisors, isolated from Android."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
FROZEN = json.loads((ROOT / 'scripts/stable111_frozen_runtime.json').read_text())['sha256']


class BootFontMaintenance(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='luoshu-boot-maintenance-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.module = self.base / 'module'
        self.common = self.module / 'common'
        (self.common / 'python/bin').mkdir(parents=True)
        (self.module / 'config').mkdir()
        (self.module / 'logs').mkdir()
        (self.module / 'module.prop').write_text('id=LuoShu\nversion=fixture\n')
        for name in ('font_manager.sh', 'task_scope.sh', 'task_scope.py', 'runtime_paths.sh',
                     'runtime_paths_lock.py', 'device_font_dynamic_guard.sh', 'device_font_template.sh'):
            shutil.copyfile(ROOT / 'common' / name, self.common / name)
        for name in ('stock_inventory_scan.py', 'font_inventory.py', 'font_check.sh'):
            (self.common / name).touch()
        self.bin = self.base / 'bin'
        self.bin.mkdir()
        getprop = self.bin / 'getprop'
        getprop.write_text('#!/bin/sh\n[ "$1" = sys.boot_completed ] && printf "%s\\n" "${FIXTURE_BOOT_COMPLETE:-0}"\n')
        getprop.chmod(0o755)
        self.scans = self.base / 'scans.jsonl'
        scanner = self.common / 'python/bin/luoshu-python'
        scanner.write_text('''#!/bin/sh
unset PYTHONHOME PYTHONPATH LD_LIBRARY_PATH
exec "$FIXTURE_HOST_PYTHON" "$FIXTURE_SCANNER" "$@"
''')
        scanner.chmod(0o755)
        self.fixture_scanner = self.base / 'scanner.py'
        self.fixture_scanner.write_text('''import json, os, signal, subprocess, sys, time
from pathlib import Path
arguments=sys.argv[1:]
output=Path(arguments[arguments.index('--output')+1])
mode=os.environ.get('FIXTURE_MODE','success')
with open(os.environ['FIXTURE_SCANS'],'a') as stream:
    stream.write(json.dumps(dict(arguments=arguments, verified=os.environ.get('LUOSHU_STOCK_VIEW_VERIFIED'),
                                 task=os.environ.get('LUOSHU_TASK_SCOPE_TASK'), output=str(output)))+'\\n')
if mode == 'reject-unverified' and os.environ.get('LUOSHU_STOCK_VIEW_VERIFIED') != '1':
    print('{"status":"error","message":"verified stock lower is unavailable"}')
    sys.exit(2)
if mode in ('hold','late-success'):
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    child=subprocess.Popen([sys.executable,'-c','import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(30)'], start_new_session=True)
    Path(os.environ['FIXTURE_CHILD']).write_text(str(child.pid))
    time.sleep(30 if mode == 'hold' else 1.3)
output.parent.mkdir(parents=True,exist_ok=True)
output.write_text('{"schema":"device-font-inventory-v1","state":"ready","fixture":"new"}')
(output.parent/'device_font_candidates.json').write_text('{"fixture":"new-candidates"}')
(output.parent/'device_font_partitions.conf').write_text('future_oem\\n')
print('{"status":"ok","slotCount":1}')
''')
        self.inventory = self.module / 'config/device_font_inventory.json'
        self.old_inventory = b'{"fixture":"old-trusted-stock"}\n'
        self.inventory.write_bytes(self.old_inventory)
        self.pending = self.module / 'config/stock_inventory_scan_pending'
        self.pending.write_text('retry-required\n')
        self.childfile = self.base / 'child.pid'
        self.lower = self.base / 'self-mount/lower/system-fonts'
        self.lower.mkdir(parents=True)
        self.lower_sentinel = self.lower / 'stock.ttf'
        self.lower_sentinel.write_bytes(b'untouched-stock-lower')
        self.env = {**os.environ, 'MODDIR': str(self.module), 'MODULE_DIR': str(self.module),
                    'PATH': str(self.bin) + os.pathsep + os.environ['PATH'],
                    'LUOSHU_TASK_SCOPE_PYTHON': sys.executable,
                    'LUOSHU_RUNTIME_PATHS_PYTHON': sys.executable,
                    'FIXTURE_HOST_PYTHON': sys.executable, 'FIXTURE_SCANNER': str(self.fixture_scanner),
                    'FIXTURE_SCANS': str(self.scans), 'FIXTURE_CHILD': str(self.childfile),
                    'LUOSHU_SELF_MOUNT_STATE_ROOT': str(self.base / 'self-mount')}
        self.addCleanup(self.assert_frozen)

    def assert_frozen(self):
        self.assertEqual({name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                          for name in FROZEN}, FROZEN)
        self.assertEqual(self.lower_sentinel.read_bytes(), b'untouched-stock-lower')

    def call_scan(self, *, early=True, mode='success', extra=None, timeout=10):
        env = {**self.env, 'FIXTURE_MODE': mode, **(extra or {})}
        if early:
            env.update(LUOSHU_STOCK_VIEW_VERIFIED='1', LUOSHU_FRESH_STOCK_SCAN='1',
                       LUOSHU_BOOT_STOCK_SCAN_TIMEOUT_SECONDS='1')
        started = time.monotonic()
        result = subprocess.run(['sh', str(self.common / 'font_manager.sh'), 'action', 'stock_scan'],
                                env=env, capture_output=True, text=True, timeout=timeout)
        return result, time.monotonic() - started

    def cleanup_proofs(self):
        proofs = [json.loads(path.read_text()) for path in self.module.glob('.luoshu-state/tasks/*.cleanup.json')]
        self.assertTrue(proofs)
        for proof in proofs:
            self.assertTrue(proof['cleaned'], proof)
            self.assertEqual(proof['leftoverPids'], [], proof)
            self.assertEqual(proof['cleanupErrors'], [], proof)
        self.assertFalse(list(self.module.glob('.luoshu-state/tasks/*.owner.json')))
        return proofs

    def scan_records(self):
        return [json.loads(line) for line in self.scans.read_text().splitlines()]

    def assert_receipt(self, result, published):
        path = self.module / 'config/boot-stock-scan.state'
        receipt = dict(line.split('=', 1) for line in path.read_text().splitlines())
        self.assertEqual(set(receipt), {'schema', 'result', 'budgetSeconds', 'elapsedSeconds', 'inventoryPublished', 'bootId'})
        self.assertEqual(receipt['schema'], 'luoshu-boot-stock-scan-v1')
        self.assertEqual(receipt['result'], result)
        self.assertEqual(receipt['inventoryPublished'], published)
        self.assertEqual(receipt['budgetSeconds'], '1')
        self.assertTrue(receipt['elapsedSeconds'].isdigit())
        self.assertEqual(receipt['bootId'], Path('/proc/sys/kernel/random/boot_id').read_text().strip())

    def test_early_success_publishes_after_clean_scope(self):
        result, elapsed = self.call_scan()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertLess(elapsed, 2)
        self.assertEqual(json.loads(self.inventory.read_text())['fixture'], 'new')
        self.assertFalse(self.pending.exists())
        self.assertEqual((self.module / 'config/device_font_partitions.conf').read_text(), 'future_oem\n')
        self.assertIn('/boot-stock-scan.', self.scan_records()[0]['output'])
        self.assertIn('--force', self.scan_records()[0]['arguments'])
        self.cleanup_proofs()
        self.assertFalse((self.module / '.stock-inventory-scan.lock').exists())
        self.assertFalse(list(self.module.glob('.luoshu-state/tmp/boot-stock-scan.*')))
        self.assert_receipt('success', 'yes')

    def test_timeout_retires_owned_children_before_return_and_keeps_inventory(self):
        result, elapsed = self.call_scan(mode='hold')
        self.assertEqual(result.returncode, 124, result.stdout + result.stderr)
        self.assertLess(elapsed, 7)
        self.assertEqual(self.inventory.read_bytes(), self.old_inventory)
        self.assertEqual(self.pending.read_text(), 'retry-required\n')
        self.assertTrue(self.childfile.exists(), 'the slow fixture must really execute')
        proof = self.cleanup_proofs()[0]
        self.assertEqual(proof['reason'], 'timeout')
        self.assertEqual(proof['result'], 124)
        self.assertGreaterEqual(proof['terminated'], 1)
        self.assertFalse((self.module / '.stock-inventory-scan.lock').exists())
        self.assertFalse(list(self.module.glob('.luoshu-state/tmp/boot-stock-scan.*')))
        self.assertNotIn('"status":"ok"', result.stdout)
        self.assert_receipt('timeout', 'no')

    def test_scanner_finishing_during_term_grace_cannot_publish_timed_out_result(self):
        result, _elapsed = self.call_scan(mode='late-success')
        self.assertEqual(result.returncode, 124, result.stdout + result.stderr)
        self.assertEqual(self.inventory.read_bytes(), self.old_inventory)
        self.assertEqual(self.pending.read_text(), 'retry-required\n')
        self.assertFalse((self.module / 'config/device_font_candidates.json').exists())
        self.assertFalse((self.module / 'config/device_font_partitions.conf').exists())
        self.cleanup_proofs()
        self.assert_receipt('timeout', 'no')

    def test_live_scan_lock_does_not_wait_or_validate_old_inventory(self):
        lock = self.module / '.stock-inventory-scan.lock'
        lock.mkdir()
        (lock / 'pid').write_text(str(os.getpid()))
        (lock / 'boot-id').write_bytes(Path('/proc/sys/kernel/random/boot_id').read_bytes())
        result, elapsed = self.call_scan()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertLess(elapsed, 1)
        self.assertEqual(self.inventory.read_bytes(), self.old_inventory)
        self.assertTrue(self.pending.exists())
        self.assertFalse(self.scans.exists())
        self.assertEqual((lock / 'pid').read_text(), str(os.getpid()))
        self.assert_receipt('busy', 'no')

    def test_unknown_lock_with_extra_file_is_nonwaiting_and_untouched(self):
        lock = self.module / '.stock-inventory-scan.lock'
        lock.mkdir()
        extra = lock / 'unknown-owner-evidence'
        extra.write_text('leave-this-lock-intact\n')
        result, elapsed = self.call_scan()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertLess(elapsed, 1)
        self.assertEqual(list(lock.iterdir()), [extra])
        self.assertEqual(extra.read_text(), 'leave-this-lock-intact\n')
        self.assertEqual(self.inventory.read_bytes(), self.old_inventory)
        self.assertTrue(self.pending.exists())
        self.assertFalse(self.scans.exists())
        self.assert_receipt('busy', 'no')

    def test_publication_failure_rolls_back_changed_metadata(self):
        candidates = self.module / 'config/device_font_candidates.json'
        partitions = self.module / 'config/device_font_partitions.conf'
        candidates.write_bytes(b'{"fixture":"old-candidates"}\n')
        partitions.write_bytes(b'old_oem\n')
        previous = (candidates.read_bytes(), partitions.read_bytes(), self.inventory.read_bytes())
        real_mv = shutil.which('mv')
        mv = self.bin / 'mv'
        mv.write_text('''#!/bin/sh
source="$2"
parent="${source%/*}"; parent="${parent##*/}"
case "$parent:${source##*/}" in
    boot-stock-scan.*:device_font_partitions.conf) exit 1 ;;
esac
exec "$FIXTURE_REAL_MV" "$@"
''')
        mv.chmod(0o755)
        result, _elapsed = self.call_scan(extra={'FIXTURE_REAL_MV': str(real_mv)})
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual((candidates.read_bytes(), partitions.read_bytes(), self.inventory.read_bytes()), previous)
        self.assertTrue(self.pending.exists())
        self.assert_receipt('failed', 'no')
        self.cleanup_proofs()
        self.assertFalse((self.module / '.stock-inventory-scan.lock').exists())
        self.assertFalse(list(self.module.glob('.luoshu-state/tmp/boot-stock-scan.*')))

    def test_publication_preflight_rejects_unsafe_destination_before_mutation(self):
        candidates = self.module / 'config/device_font_candidates.json'
        candidates.write_bytes(b'{"fixture":"old-candidates"}\n')
        partitions = self.module / 'config/device_font_partitions.conf'
        outside = self.base / 'outside'
        outside.write_bytes(b'leave-outside-data-alone')
        partitions.symlink_to(outside)
        result, _elapsed = self.call_scan()
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(candidates.read_bytes(), b'{"fixture":"old-candidates"}\n')
        self.assertEqual(self.inventory.read_bytes(), self.old_inventory)
        self.assertEqual(outside.read_bytes(), b'leave-outside-data-alone')
        self.assertTrue(partitions.is_symlink())
        self.assertTrue(self.pending.exists())
        self.assert_receipt('failed', 'no')

    def test_real_frozen_post_mount_continues_only_after_timeout_cleanup(self):
        shutil.copyfile(ROOT / 'post-mount.sh', self.module / 'post-mount.sh')
        (self.module / 'config/font_runtime_legacy_v14_4.conf').write_text('enabled=true\nfont=mix\n')
        (self.common / 'private_payload.sh').write_text('luoshu_private_mount_module_view() { return 0; }\n')
        marker = self.base / 'mount-called'
        (self.common / 'mount_compat.sh').write_text('''luoshu_private_self_mount_ensure() {
    cmp -s "$MODDIR/config/device_font_inventory.json" "$FIXTURE_OLD_INVENTORY" || return 1
    [ -f "$MODDIR/config/stock_inventory_scan_pending" ] || return 1
    printf 'mounted-after-scan-return\\n' > "$FIXTURE_MOUNT_CALLED"
    return 0
}
''')
        old = self.base / 'old-inventory'
        old.write_bytes(self.old_inventory)
        started = time.monotonic()
        result = subprocess.run(['sh', str(self.module / 'post-mount.sh')], env={**self.env,
                                'FIXTURE_MODE': 'hold', 'LUOSHU_BOOT_STOCK_SCAN_TIMEOUT_SECONDS': '1',
                                'FIXTURE_OLD_INVENTORY': str(old), 'FIXTURE_MOUNT_CALLED': str(marker)},
                                capture_output=True, text=True, timeout=10)
        elapsed = time.monotonic() - started
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertLess(elapsed, 7)
        self.assertTrue(marker.exists(), 'the actual frozen router must proceed to mount')
        self.assertEqual(self.inventory.read_bytes(), self.old_inventory)
        self.assertTrue(self.pending.exists())
        self.assert_receipt('timeout', 'no')
        self.assertEqual(self.cleanup_proofs()[0]['reason'], 'timeout')

    def test_unconfirmed_cleanup_keeps_stage_identity_inventory_and_pending(self):
        scope = self.common / 'task_scope.py'
        source = scope.read_text()
        marker = 'def remove_temporary(record):\n'
        assert marker in source
        original_source = source
        scope.write_text(source.replace(marker, marker + "    raise RuntimeError('fixture cleanup denied')\n", 1))
        result, _elapsed = self.call_scan()
        self.assertEqual(result.returncode, 125, result.stdout + result.stderr)
        self.assertEqual(self.inventory.read_bytes(), self.old_inventory)
        self.assertTrue(self.pending.exists())
        self.assert_receipt('cleanup-pending', 'no')
        self.assertTrue(list(self.module.glob('.luoshu-state/tmp/boot-stock-scan.*')))
        self.assertTrue(list(self.module.glob('.luoshu-state/tasks/*.owner.json')))
        self.assertTrue((self.module / '.stock-inventory-scan.lock').exists())
        proof = json.loads(next(self.module.glob('.luoshu-state/tasks/*.cleanup.json')).read_text())
        self.assertFalse(proof['cleaned'])
        self.assertEqual(proof['cleanupErrors'], ['fixture cleanup denied'])
        scan_count = len(self.scan_records())
        stages = list(self.module.glob('.luoshu-state/tmp/boot-stock-scan.*'))
        lock = self.module / '.stock-inventory-scan.lock'
        lock_evidence = {path.name: path.read_bytes() for path in lock.iterdir()}
        # Restore the normal supervisor: the next foreground refusal must come
        # from the unresolved old lease, not this test's injected cleanup fault.
        scope.write_text(original_source)
        retried, elapsed = self.call_scan(early=False)
        self.assertEqual(retried.returncode, 125, retried.stdout + retried.stderr)
        self.assertLess(elapsed, 2)
        self.assertEqual(len(self.scan_records()), scan_count, 'no new scanner may take over the old unresolved lease')
        self.assertEqual({path.name: path.read_bytes() for path in lock.iterdir()}, lock_evidence)
        self.assertEqual(list(self.module.glob('.luoshu-state/tmp/boot-stock-scan.*')), stages)
        self.assertEqual(self.inventory.read_bytes(), self.old_inventory)
        self.assertTrue(self.pending.exists())

    def test_waiting_foreground_does_not_validate_and_clear_pending_after_boot_timeout(self):
        lock = self.module / '.stock-inventory-scan.lock'
        lock.mkdir()
        (lock / 'pid').write_text(str(os.getpid()))
        (lock / 'boot-id').write_bytes(Path('/proc/sys/kernel/random/boot_id').read_bytes())
        process = subprocess.Popen(['sh', str(self.common / 'font_manager.sh'), 'action', 'stock_scan'],
                                   env={**self.env, 'FIXTURE_MODE': 'success'},
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            time.sleep(.3)
            (lock / 'pid').unlink()
            (lock / 'boot-id').unlink()
            lock.rmdir()
            stdout, stderr = process.communicate(timeout=5)
        finally:
            if process.poll() is None:
                process.terminate()
                process.communicate(timeout=8)
        self.assertEqual(process.returncode, 0, stdout + stderr)
        record = self.scan_records()[0]
        self.assertNotIn('--validate', record['arguments'])
        self.assertIn('--scan', record['arguments'])
        self.assertEqual(json.loads(self.inventory.read_text())['fixture'], 'new')
        self.assertFalse(self.pending.exists())
        self.cleanup_proofs()

    def test_after_boot_cannot_reuse_pre_mount_verified_flag(self):
        result, _elapsed = self.call_scan(mode='reject-unverified', extra={'FIXTURE_BOOT_COMPLETE': '1'})
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIsNone(self.scan_records()[0]['verified'])
        self.assertEqual(self.inventory.read_bytes(), self.old_inventory)
        self.assertTrue(self.pending.exists())
        self.cleanup_proofs()

    def test_already_mounted_before_boot_complete_cannot_reuse_verified_flag(self):
        (self.module / 'config/self-mount.conf').write_text('state=mounted\n')
        (self.base / 'self-mount/boot-id').write_bytes(Path('/proc/sys/kernel/random/boot_id').read_bytes())
        result, _elapsed = self.call_scan(mode='reject-unverified')
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertFalse(self.scans.exists(), 'early unverified roots must not create a bind snapshot')
        self.assertEqual(self.inventory.read_bytes(), self.old_inventory)
        self.assertTrue(self.pending.exists())
        self.assert_receipt('failed', 'no')

    def test_failed_same_boot_mount_verification_fast_refuses_stock_assertion(self):
        (self.module / 'config/self-mount.conf').write_text('state=failed\nbackend=verification\nmounted=system/fonts:overlay\n')
        (self.base / 'self-mount/boot-id').write_bytes(Path('/proc/sys/kernel/random/boot_id').read_bytes())
        result, elapsed = self.call_scan(mode='reject-unverified')
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertLess(elapsed, 1)
        self.assertFalse(self.scans.exists())
        self.assertEqual(self.inventory.read_bytes(), self.old_inventory)
        self.assertTrue(self.pending.exists())
        self.assert_receipt('failed', 'no')

    def test_unknown_mount_state_or_idle_with_components_cannot_enter_early_scanner(self):
        for state in ('state=unexpected\n', 'state=idle\nmounted=system/fonts:bind\n'):
            (self.module / 'config/self-mount.conf').write_text(state)
            result, _elapsed = self.call_scan(mode='reject-unverified')
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertFalse(self.scans.exists())
            self.assertEqual(self.inventory.read_bytes(), self.old_inventory)
            self.assertTrue(self.pending.exists())
            self.assert_receipt('failed', 'no')

    def test_foreground_keeps_existing_900_second_scope_and_full_scan(self):
        # Observe the real run() arguments, without waiting for that whole budget.
        scope = self.common / 'task_scope.py'
        source = scope.read_text()
        marker = 'def run(args):\n'
        assert marker in source
        source = source.replace(marker, marker + "    Path(os.environ['FIXTURE_SCOPE_BUDGET']).write_text(str(args.timeout))\n", 1)
        scope.write_text(source)
        budget = self.base / 'budget'
        result, _elapsed = self.call_scan(early=False, extra={'FIXTURE_SCOPE_BUDGET': str(budget)})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(budget.read_text(), '900.0')
        self.assertIn('--force', self.scan_records()[0]['arguments'])
        self.assertEqual(self.scan_records()[0]['output'], str(self.inventory))
        self.cleanup_proofs()

    def release_probe(self, *, service=False, state='missing'):
        (self.common / 'device_font_template.sh').write_text('# fixture\n')
        target = self.base / 'dynamic.xml'
        source = self.module / 'system/etc/.luoshu-data-fonts-config.xml'
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text('sanitized\n')
        target.write_text('sanitized\n')
        if state != 'missing':
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            (self.module / 'config/device-font-dynamic-mount.conf').write_text(
                'source=system/etc/.luoshu-data-fonts-config.xml\n' + f'target={target}\nsourceSha256={digest}\n')
        service_path = self.module / '.luoshu-runtime/core/service.sh'
        # Execute the actual frozen service's entire release/ensure block.
        frozen = (ROOT / '.luoshu-runtime/core/service.sh').read_text()
        block = frozen[frozen.index('    _dynamic_template_safe=1'):frozen.index('    # 刷写阶段')]
        body = '''. "$MODDIR/common/device_font_dynamic_guard.sh"
_dfpr_module() { printf '%s\\n' "$MODDIR"; }
_dfpr_log() { :; }
log_service() { printf 'service:%s:%s\\n' "$1" "$2"; }
TEMPLATE_CALLS=0; VERIFY_CALLS=0
sh() { case "$1" in */device_font_template.sh) TEMPLATE_CALLS=$((TEMPLATE_CALLS+1)); return 2 ;; *) return 1 ;; esac; }
device_font_load_verify() { VERIFY_CALLS=$((VERIFY_CALLS+1)); return 2; }
_dfpr_dynamic_mount_exists() { [ "$FIXTURE_RELEASE_STATE" = failed ] || [ "$FIXTURE_RELEASE_STATE" = mounted ]; }
_dfpr_hash() { sha256sum "$1" | awk '{print $1}'; }
umount() { [ "$FIXTURE_RELEASE_STATE" != failed ] || return 1; FIXTURE_RELEASE_STATE=released; return 0; }
'''
        if service:
            body += block + '\nprintf "counts:%s:%s\\n" "$TEMPLATE_CALLS" "$VERIFY_CALLS"\n'
        else:
            body += 'device_font_dynamic_mount_release; printf "release:%s counts:%s:%s\\n" "$?" "$TEMPLATE_CALLS" "$VERIFY_CALLS"\n'
        return subprocess.run(['sh', '-c', body, str(service_path if service else self.base / 'standalone.sh')],
                              env={**self.env, 'LUOSHU_DATA_FONTS_CONFIG_TARGET': str(target),
                                   'FIXTURE_RELEASE_STATE': state}, capture_output=True, text=True, timeout=3)

    def test_actual_frozen_service_has_one_ensure_and_no_release_verify(self):
        result = self.release_probe(service=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('counts:1:0', result.stdout)
        # Preserve the real frozen service's error; no rc=2 becomes false success.
        self.assertIn('service:ERROR:', result.stdout)

    def test_standalone_release_keeps_existing_maintenance(self):
        result = self.release_probe()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('release:2 counts:1:1', result.stdout)

    def test_verified_unmount_in_service_still_runs_ensure_once(self):
        result = self.release_probe(service=True, state='mounted')
        self.assertIn('counts:1:0', result.stdout)
        self.assertIn('service:INFO:已释放', result.stdout)
        self.assertIn('service:ERROR:', result.stdout)

    def test_failed_release_is_not_converted_to_success(self):
        result = self.release_probe(service=True, state='failed')
        self.assertIn('counts:0:0', result.stdout)
        self.assertIn('service:ERROR:动态字体临时视图无法安全释放', result.stdout)
        standalone = self.release_probe(state='failed')
        self.assertIn('release:1 counts:0:0', standalone.stdout)

    def test_busy_template_lock_is_pending_and_preserves_old_snapshot(self):
        old = self.module / 'config/device-font-template.json'
        old.write_bytes(b'{"captureRevision":1,"fixture":"old-snapshot"}')
        original = old.read_bytes()
        (self.module / 'config/active_font.conf').write_text('default\n')
        lock = self.module / '.device-font-template.lock'
        lock.mkdir()
        (lock / 'sentinel').write_text('unknown-owner\n')
        result = subprocess.run(['sh', str(self.common / 'device_font_template.sh'), 'ensure'],
                                env=self.env, capture_output=True, text=True, timeout=3)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertEqual(old.read_bytes(), original)
        self.assertEqual((lock / 'sentinel').read_text(), 'unknown-owner\n')
        pending = self.module / 'config/device-font-template-pending.conf'
        self.assertIn('reason=template-capture-busy', pending.read_text())
        self.assertIn('state=pending-stock-boot', pending.read_text())


if __name__ == '__main__':
    if len(sys.argv) > 1:
        ROOT = Path(sys.argv.pop(1)).resolve()
        FROZEN = json.loads((Path(__file__).resolve().parent / 'stable111_frozen_runtime.json').read_text())['sha256']
    unittest.main()
