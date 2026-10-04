import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from app_anr import PACKAGE, MAX_TRACE_BYTES, capture_owned_anr, owned_trace_blocks, target_anr


def trace(package, pid=3461, complete=True):
    return (f'----- pid {pid} at 2026-10-04 02:45:19 -----\n'
            f'Cmd line: {package}\n'
            '"main" prio=5 tid=1 Native\n  at example.Frame.draw(Frame.java:12)\n'
            + (f'----- end {pid} -----\n' if complete else ''))


class TargetAnrTests(unittest.TestCase):
    def test_actual_fourth_root_reason_is_detected(self):
        fixture = Path(__file__).resolve().parents[2] / 'docs/evidence/root-final-anr-37169987413.txt'
        self.assertTrue(target_anr(fixture.read_text()))

    def test_log_header_and_process_suffix_detected(self):
        self.assertTrue(target_anr('ActivityManager: ANR in ' + PACKAGE + ' (pid 3461)'))
        self.assertTrue(target_anr('Reason: executing service ' + PACKAGE + ':worker'))

    def test_other_anr_metadata_does_not_implicate_target(self):
        report = 'Reason: Input dispatching timed out (com.android.systemui/window)\npackageName=' + PACKAGE
        self.assertFalse(target_anr(report))
        self.assertFalse(target_anr('  topResumedActivity=' + PACKAGE + '/MainActivity'))
        self.assertFalse(target_anr('(nothing)'))

    def test_package_prefix_siblings_are_not_target(self):
        for suffix in ('extra', '.other', '_test'):
            self.assertFalse(target_anr('ANR in ' + PACKAGE + suffix))
            self.assertFalse(target_anr('Reason: Input dispatching timed out (' + PACKAGE + suffix + '/Main)'))
        self.assertFalse(target_anr('Reason: Input dispatching timed out (other.' + PACKAGE + '/Main)'))


class OwnedTraceTests(unittest.TestCase):
    def test_mixed_dump_keeps_only_exact_target(self):
        raw = trace('com.android.systemui', 20) + trace(PACKAGE) + trace(PACKAGE + ':worker', 30)
        blocks = owned_trace_blocks(raw)
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]['pid'], 3461)
        self.assertTrue(blocks[0]['complete'])
        self.assertEqual(blocks[0]['text'], trace(PACKAGE))

    def test_incomplete_owned_block_remains_incomplete(self):
        blocks = owned_trace_blocks(trace(PACKAGE, complete=False) + trace('com.android.systemui', 21))
        self.assertEqual(len(blocks), 1)
        self.assertFalse(blocks[0]['complete'])
        self.assertNotIn('systemui', blocks[0]['text'])

    def test_missing_or_wrong_command_and_wrong_end_are_rejected(self):
        self.assertEqual(owned_trace_blocks('Cmd line: ' + PACKAGE), [])
        self.assertEqual(owned_trace_blocks(trace(PACKAGE + '.other')), [])
        block = owned_trace_blocks(trace(PACKAGE).replace('end 3461', 'end 22'))[0]
        self.assertFalse(block['complete'])

    def test_collector_uses_existing_avd_root_and_exports_only_owned_blocks(self):
        raw = (trace('com.android.systemui', 20) + trace(PACKAGE)).encode()
        responses = [subprocess.CompletedProcess([], 0, b'/data/anr/anr_2026-10-04\n/elsewhere/anr_fake\n', b''),
                     subprocess.CompletedProcess([], 0, raw, b'')]
        with tempfile.TemporaryDirectory() as tmp, patch('app_anr.subprocess.run', side_effect=responses) as run:
            result = capture_owned_anr('adb', '/data/local/tmp/luoshu-magisk/magisk', tmp, 'failure')
            self.assertEqual(result['result'], 'CAPTURED')
            self.assertEqual(len(result['files']), 1)
            self.assertEqual((Path(tmp) / result['files'][0]['file']).read_text(), trace(PACKAGE))
            self.assertEqual(result['reads'][1]['sha256'], hashlib.sha256(raw).hexdigest())
            self.assertNotIn('stdout', result['reads'][1])
            args = run.call_args_list[1].args[0]
            self.assertEqual(args[:4], ['adb', '-s', 'emulator-5554', 'shell'])
            self.assertIn(' su -mm -c ', args[4])
            self.assertIn('head -c ' + str(MAX_TRACE_BYTES), args[4])
            self.assertNotIn('/elsewhere/', args[4])

    def test_missing_trace_stays_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp, patch('app_anr.subprocess.run', return_value=subprocess.CompletedProcess([], 1, b'', b'No such file')):
            result = capture_owned_anr('adb', 'magisk', tmp, 'failure')
        self.assertEqual(result['result'], 'NOT_AVAILABLE_WITH_ERRORS')
        self.assertEqual(result['files'], [])

    def test_collector_bounds_number_of_files(self):
        responses = [subprocess.CompletedProcess([], 0, ''.join(f'/data/anr/anr_{i}\n' for i in range(5)).encode(), b'')]
        responses += [subprocess.CompletedProcess([], 0, trace(PACKAGE).encode(), b'') for _ in range(4)]
        with tempfile.TemporaryDirectory() as tmp, patch('app_anr.subprocess.run', side_effect=responses) as run:
            result = capture_owned_anr('adb', 'magisk', tmp, 'failure')
        self.assertEqual(len(result['files']), 4)
        self.assertEqual(run.call_count, 5)
        self.assertFalse(any('anr_4' in read['query'] for read in result['reads']))

    def test_read_timeout_is_diagnostic_error_not_success(self):
        with tempfile.TemporaryDirectory() as tmp, patch('app_anr.subprocess.run', side_effect=subprocess.TimeoutExpired('adb', 20)):
            result = capture_owned_anr('adb', 'magisk', tmp, 'failure')
        self.assertEqual(result['result'], 'NOT_AVAILABLE_WITH_ERRORS')
        self.assertTrue(result['errors'])


if __name__ == '__main__':
    unittest.main()
