#!/usr/bin/env python3
"""Exercise the exact read-only App summary shell with local, sanitized fixtures."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/logs/DiagnosticExportUi.kt'


class BootSummaryTest(unittest.TestCase):
    def report(self, values=None, files=()):
        with tempfile.TemporaryDirectory(prefix='luoshu-summary-') as td:
            base = Path(td)
            module = base / 'module'
            config = module / 'config'
            config.mkdir(parents=True)
            (module / 'logs').mkdir()
            for name, body in (values or {}).items():
                (config / name).write_text(body)
            for name in files:
                (config / name).touch()
            (module / 'module.prop').write_text('version=2.2.2\nversionCode=70202\n')
            bindir = base / 'bin'
            bindir.mkdir()
            (bindir / 'getprop').write_text('#!/bin/sh\ncase "$1" in sys.boot_completed) echo 1 ;; ro.build.version.sdk) echo 36 ;; esac\n')
            (bindir / 'getprop').chmod(0o755)
            source = SOURCE.read_text()
            command = source.split('val command = """', 1)[1].split('""".trimIndent()', 1)[0]
            command = command.replace("${'$'}", '$').replace('MOD=/data/adb/modules/LuoShu', 'MOD=' + str(module))
            command = command.replace('OUT_DIR=/sdcard/LuoShu/reports', 'OUT_DIR=' + str(base / 'reports'))
            result = subprocess.run(['sh', '-c', command], env=dict(os.environ, PATH=str(bindir) + ':' + os.environ['PATH']),
                                    capture_output=True, text=True, timeout=5)
            self.assertEqual(0, result.returncode, result.stderr)
            body = Path(result.stdout.strip()).read_text()
            return dict(line.split('=', 1) for line in body.splitlines() if '=' in line), body

    def test_missing_evidence_stays_unknown(self):
        report, _ = self.report()
        self.assertEqual('unknown', report['bootScanResult'])
        self.assertEqual('unknown', report['bootScanElapsedSeconds'])
        self.assertEqual('unknown', report['templateCaptureRevision'])
        self.assertEqual('no', report['legacyMode'])
        self.assertEqual('none', report['templatePendingState'])

    def test_pending_reason_removes_user_font_name(self):
        report, body = self.report({'device-font-template-pending.conf': 'state=pending-stock-boot\nreason=active-font:Private-Font-Name\nactiveFont=Private-Font-Name\n'})
        self.assertEqual('active-font', report['templatePendingReason'])
        self.assertNotIn('Private-Font-Name', body)
        self.assertEqual('pending-stock-boot', report['templatePendingState'])

    def test_timeout_receipt_does_not_claim_whole_phone_duration(self):
        report, _ = self.report({'boot-stock-scan.state': 'schema=luoshu-boot-stock-scan-v1\nresult=timeout\nbudgetSeconds=3\nelapsedSeconds=5\ninventoryPublished=no\n'},
                                files=['stock_inventory_scan_pending'])
        self.assertEqual('timeout', report['bootScanResult'])
        self.assertEqual('no', report['bootScanInventoryPublished'])
        self.assertEqual('yes', report['stockScanPending'])
        self.assertIn('not phone boot duration', report['bootScanTimingScope'])

    def test_unexpected_receipt_tokens_and_private_paths_are_not_exported(self):
        report, body = self.report({'boot-stock-scan.state': 'schema=luoshu-boot-stock-scan-v1\nresult=/private/user-secret\nbudgetSeconds=1;token\nelapsedSeconds=/data/user/0/secret\ninventoryPublished=private\n',
                                   'device-font-template-pending.conf': 'state=secret\nreason=/private/document\n',
                                   'device-font-template.state': 'state=trusted\ncaptureRevision=/private/secret\n'})
        for key in ('bootScanResult', 'bootScanBudgetSeconds', 'bootScanElapsedSeconds', 'bootScanInventoryPublished',
                    'templatePendingState', 'templatePendingReason', 'templateCaptureRevision'):
            self.assertEqual('unknown', report[key], key)
        self.assertNotIn('/private/', body)
        self.assertNotIn('1;token', body)
        self.assertNotIn('/data/user/0/', body)

    def test_boot_modes_are_presence_and_allowlist_only(self):
        report, body = self.report({'font-payload-boot.conf': 'state=booting\nfont=Private-Font-Name\n',
                                   'device-font-template.state': 'state=trusted\ncaptureRevision=2\n'},
                                  files=['font_runtime_legacy_v14_4.conf', 'text_reboot_required.conf'])
        self.assertEqual('yes', report['legacyMode'])
        self.assertEqual('yes', report['rebootPending'])
        self.assertEqual('booting', report['payloadBootState'])
        self.assertEqual('2', report['templateCaptureRevision'])
        self.assertNotIn('Private-Font-Name', body)

    def test_unknown_schema_cannot_claim_success(self):
        report, _ = self.report({'boot-stock-scan.state': 'schema=future-schema\nresult=success\nbudgetSeconds=3\nelapsedSeconds=2\ninventoryPublished=yes\n'})
        self.assertEqual('unknown', report['bootScanResult'])
        self.assertEqual('unknown', report['bootScanReceiptSchema'])
        self.assertEqual('unknown', report['bootScanInventoryPublished'])

    def test_boot_identity_is_compared_but_not_exported(self):
        boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        report, body = self.report({'boot-stock-scan.state': 'schema=luoshu-boot-stock-scan-v1\nresult=success\nbudgetSeconds=3\nelapsedSeconds=2\ninventoryPublished=yes\nbootId=' + boot + '\n'})
        self.assertEqual('yes', report['bootScanCurrentBoot'])
        self.assertNotIn(boot, body)
        old, _ = self.report({'boot-stock-scan.state': 'schema=luoshu-boot-stock-scan-v1\nresult=success\nbootId=prior-boot\n'})
        self.assertEqual('no', old['bootScanCurrentBoot'])

    def test_success_requires_explicit_published_receipt(self):
        report, _ = self.report({'boot-stock-scan.state': 'schema=luoshu-boot-stock-scan-v1\nresult=success\nbudgetSeconds=3\nelapsedSeconds=2\ninventoryPublished=yes\n'})
        self.assertEqual('success', report['bootScanResult'])
        self.assertEqual('yes', report['bootScanInventoryPublished'])
        self.assertEqual('1', report['sysBootCompleted'])
        self.assertTrue(report['uptimeSeconds'].isdigit())


if __name__ == '__main__':
    unittest.main()
