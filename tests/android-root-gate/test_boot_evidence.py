import tempfile
import unittest
from pathlib import Path
from boot_evidence import DIAGNOSTICS, PROBE, wait_for_reboot


class Clock:
    def __init__(self):
        self.value = 0
    def now(self):
        return self.value
    def sleep(self, seconds):
        self.value += seconds


class RebootEvidenceTests(unittest.TestCase):
    def test_old_completed_transport_is_not_a_new_boot(self):
        probes = iter(['old\n1\nEnforcing', 'new\n\nEnforcing',
                       'new\n1\nEnforcing', 'new\n1\nEnforcing'])
        calls, grants = [], []
        def command(args, **kwargs):
            calls.append(args)
            return next(probes) if args == ['shell', PROBE] else ''
        clock = Clock(); report = {}
        with tempfile.TemporaryDirectory() as output:
            result = wait_for_reboot(command, lambda: grants.append(True), 'old', output,
                                    report, clock=clock.now, sleep=clock.sleep)
        self.assertEqual({'before': 'old', 'after': 'new'}, result)
        self.assertEqual([True], grants)
        self.assertEqual('PASS', report['boot_attempts'][0]['result'])
        self.assertFalse(any(args in DIAGNOSTICS.values() for args in calls))
        self.assertEqual(4, clock.value)

    def test_boot_timeout_keeps_current_boot_evidence_without_calling_it_pass(self):
        clock = Clock(); report = {}
        def command(args, **kwargs):
            if args == ['shell', PROBE]:
                return 'new\n\nEnforcing'
            return 'evidence for ' + ' '.join(args)
        with tempfile.TemporaryDirectory() as output:
            with self.assertRaisesRegex(RuntimeError, 'did not complete'):
                wait_for_reboot(command, lambda: self.fail('root not ready'), 'old', output,
                                report, seconds=5, clock=clock.now, sleep=clock.sleep)
            attempt = report['boot_attempts'][0]
            self.assertEqual('FAIL', attempt['result'])
            self.assertEqual(4, len(attempt['evidence_files']))
            self.assertTrue(all((Path(output) / name).is_file() for name in attempt['evidence_files']))
        self.assertEqual(5, clock.value)

    def test_offline_transport_can_recover_within_same_deadline(self):
        clock = Clock(); probes = 0
        def command(args, **kwargs):
            nonlocal probes
            if args == ['shell', PROBE]:
                probes += 1
                if probes == 1:
                    raise TimeoutError('same emulator offline')
                return 'new\n1\nEnforcing'
            return ''
        report = {}
        with tempfile.TemporaryDirectory() as output:
            self.assertEqual('new', wait_for_reboot(command, lambda: None, 'old', output,
                report, clock=clock.now, sleep=clock.sleep)['after'])
        self.assertIn('offline', report['boot_attempts'][0]['last_transport_error'])

    def test_diagnostic_failure_does_not_hide_reboot_or_selinux_failure(self):
        def command(args, **kwargs):
            if args == ['reboot']:
                return ''
            if args == ['shell', PROBE]:
                return 'new\n1\nPermissive'
            raise TimeoutError('diagnostic timeout')
        report = {}
        with tempfile.TemporaryDirectory() as output:
            with self.assertRaisesRegex(RuntimeError, 'SELinux'):
                wait_for_reboot(command, lambda: self.fail('root forbidden'), 'old', output, report)
        self.assertEqual(4, len(report['boot_attempts'][0]['diagnostic_errors']))

    def test_second_reboot_during_root_check_fails_identity_binding(self):
        probes = iter(['new\n1\nEnforcing', 'another\n1\nEnforcing'])
        def command(args, **kwargs):
            return next(probes) if args == ['shell', PROBE] else ''
        report = {}
        with tempfile.TemporaryDirectory() as output:
            with self.assertRaisesRegex(RuntimeError, 'identity changed'):
                wait_for_reboot(command, lambda: None, 'old', output, report)
        self.assertEqual('FAIL', report['boot_attempts'][0]['result'])

    def test_unwritable_diagnostic_destination_preserves_original_failure(self):
        def command(args, **kwargs):
            return 'new\n1\nPermissive' if args == ['shell', PROBE] else ''
        report = {}
        with tempfile.TemporaryDirectory() as output:
            (Path(output) / 'boot-failures').write_text('file blocks evidence directory')
            with self.assertRaisesRegex(RuntimeError, 'SELinux'):
                wait_for_reboot(command, lambda: None, 'old', output, report)
        self.assertEqual(4, len(report['boot_attempts'][0]['diagnostic_errors']))


if __name__ == '__main__':
    unittest.main()
