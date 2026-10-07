#!/usr/bin/env python3
"""Exercise transport identities/deadlines, not an invented accessibility tree."""
import json
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from ui_snapshot_session import HELPER, ROOT_WAIT_MS, UiSnapshotSession


class Clock:
    def __init__(self):
        self.now = 100.0

    def monotonic(self):
        return self.now

    def sleep(self, duration):
        self.now += duration


class PrivateProtocol:
    """Simulate only private-file adb I/O. XML bytes have no UI semantics."""
    def __init__(self, session, clock):
        self.session = session
        self.clock = clock
        self.files = {
            'ready.json': json.dumps({'protocol': 1, 'nonce': session.nonce,
                                     'state': 'ready', 'root_wait_ms': ROOT_WAIT_MS}).encode(),
            'closed.json': json.dumps({'protocol': 1, 'nonce': session.nonce, 'state': 'closed'}).encode(),
        }
        self.response_transform = lambda value: value
        self.ready_delay = 0
        self.requests = []
        self.xml_reads = []
        self.calls = []
        self.xml = b'unchanged bytes read from the matching private XML file'

    def run(self, command, *, input, capture_output, timeout):
        self.calls.append((command, timeout))
        self.clock.now += min(.1, timeout)
        args = command[len(self.session.adb_command):]
        if args[:2] == ['shell', '-T']:
            remote = shlex.split(args[-1])[0]
            basename = remote.split(' > ', 1)[1].split('.tmp', 1)[0].rsplit('/', 1)[1]
            value = json.loads(input)
            self.files[basename] = input
            if basename.startswith('request-'):
                self.requests.append(value)
                result = {'snapshot': 'ok', 'filename': value['filename'], 'nodes': '2',
                          'wait_ms': '1200', 'attempts': '13', 'root_source': 'focused-window:7'}
                response = {**value, 'code': -1, 'result': result}
                response = self.response_transform(response)
                if response is not None:
                    self.files['response-' + value['request_id'] + '.json'] = (
                        response if isinstance(response, bytes) else json.dumps(response).encode())
                self.files[value['filename']] = self.xml
            return subprocess.CompletedProcess(command, 0, b'', b'')
        if args[:4] == ['shell', 'run-as', HELPER, 'cat']:
            basename = args[4].rsplit('/', 1)[1]
            if basename == 'ready.json' and self.clock.now < 100 + self.ready_delay:
                return subprocess.CompletedProcess(command, 1, b'', b'not ready')
            if basename.endswith('.xml'):
                self.xml_reads.append(args[4])
            value = self.files.get(basename)
            return subprocess.CompletedProcess(command, 0 if value is not None else 1,
                                               value or b'', b'')
        if args[:4] == ['shell', 'run-as', HELPER, 'rm']:
            return subprocess.CompletedProcess(command, 0, b'', b'')
        if args == ['shell', 'am', 'force-stop', HELPER]:
            return subprocess.CompletedProcess(command, 0, b'', b'')
        raise AssertionError(f'Unexpected adb transport command: {args}')


class UiSnapshotSessionTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.output = Path(self.temporary.name)
        self.session = UiSnapshotSession(['adb', '-s', 'emulator-5554'], self.output)
        self.clock = Clock()
        self.protocol = PrivateProtocol(self.session, self.clock)
        self.process = Mock()
        self.process.poll.return_value = None
        self.process.returncode = 0
        self.process.communicate.return_value = (b'INSTRUMENTATION_CODE: -1\n', b'')
        self.popen = self.enterContext(patch('ui_snapshot_session.subprocess.Popen', return_value=self.process))
        self.adb = self.enterContext(patch('ui_snapshot_session.subprocess.run', side_effect=self.protocol.run))
        self.enterContext(patch('ui_snapshot_session.time.monotonic', side_effect=self.clock.monotonic))
        self.enterContext(patch('ui_snapshot_session.time.sleep', side_effect=self.clock.sleep))

    def test_one_connection_unique_requests_matching_xml_and_normal_finish(self):
        for index in (1, 2):
            metadata, xml = self.session.capture(f'hierarchy-{index:04d}.xml')
            self.assertEqual('1200', metadata['wait_ms'])
            self.assertEqual(self.protocol.xml.decode(), xml)
        self.popen.assert_called_once()
        self.assertEqual(2, len({value['request_id'] for value in self.protocol.requests}))
        self.assertTrue(all(value['nonce'] == self.session.nonce and value['root_wait_ms'] == 8000
                            for value in self.protocol.requests))
        self.assertEqual([f'{self.session.directory}/hierarchy-{index:04d}.xml' for index in (1, 2)],
                         self.protocol.xml_reads)
        self.session.close()
        self.process.communicate.assert_called_once_with(timeout=10)
        self.assertNotIn(['adb', '-s', 'emulator-5554', 'shell', 'am', 'force-stop', HELPER],
                         [command for command, _ in self.protocol.calls])
        journal = json.loads((self.output / 'ui-snapshot-session.json').read_text())
        self.assertEqual('closed', journal['events'][-1]['event'])
        self.assertTrue(all('monotonic_seconds' in event for event in journal['events']))
        self.assertTrue((self.output / 'ui-snapshot-session-instrumentation.txt').is_file())

    def test_response_identity_and_budget_mismatches_cannot_read_xml_or_restart(self):
        for key, value in [('nonce', '0' * 32), ('request_id', '0' * 32), ('filename', 'hierarchy-9999.xml'),
                           ('root_wait_ms', 8001), ('protocol', True)]:
            with self.subTest(key=key):
                session = UiSnapshotSession(self.session.adb_command, self.output)
                protocol = PrivateProtocol(session, self.clock)
                protocol.response_transform = lambda response: {**response, key: value}
                with patch('ui_snapshot_session.subprocess.run', side_effect=protocol.run):
                    with self.assertRaisesRegex(RuntimeError, 'mismatch'):
                        session.capture('hierarchy-0001.xml')
                    with self.assertRaises(RuntimeError):
                        session.capture('hierarchy-0002.xml')
                self.assertEqual([], protocol.xml_reads)
                self.assertEqual(1, len(protocol.requests))
        self.assertEqual(5, self.popen.call_count)

    def test_result_filename_or_code_disagreement_cannot_read_xml(self):
        for transform in [lambda response: {**response, 'code': 0},
                          lambda response: {**response, 'code': True},
                          lambda response: {**response, 'result': {**response['result'], 'filename': 'hierarchy-9999.xml'}}]:
            with self.subTest(transform=transform):
                session = UiSnapshotSession(self.session.adb_command, self.output)
                protocol = PrivateProtocol(session, self.clock)
                protocol.response_transform = transform
                with patch('ui_snapshot_session.subprocess.run', side_effect=protocol.run):
                    with self.assertRaises(RuntimeError):
                        session.capture('hierarchy-0001.xml')
                self.assertEqual([], protocol.xml_reads)

    def test_failed_real_root_wait_preserves_metadata_without_reading_xml(self):
        failure = {'snapshot': 'failed', 'error': 'No visible accessibility descendants within 8s',
                   'wait_ms': '8001', 'attempts': '62', 'last_root_window_id': '-1',
                   'last_root_child_count': '2', 'last_root_visible_child_count': '0',
                   'root_refresh_failures': '1', 'root_observations': '[]', 'window_counts': '[]'}
        self.protocol.response_transform = lambda response: {**response, 'code': 0, 'result': failure}
        metadata, xml = self.session.capture('hierarchy-0001.xml')
        self.assertEqual(failure, metadata)
        self.assertIsNone(xml)
        self.assertEqual([], self.protocol.xml_reads)
        raw = json.loads((self.output / 'hierarchy-0001-session-response.json').read_text())
        self.assertEqual(failure, raw['result'])
        self.session.close()
        self.popen.assert_called_once()

    def test_duplicate_or_invalid_filename_cannot_create_a_new_request(self):
        self.session.capture('hierarchy-0001.xml')
        for name in ('hierarchy-0001.xml', '../old.xml'):
            with self.assertRaises((RuntimeError, ValueError)):
                self.session.capture(name)
        self.assertEqual(1, len(self.protocol.requests))

    def test_nonobject_or_malformed_response_fails_with_raw_evidence(self):
        for response in (b'[]', b'null', b'{broken'):
            with self.subTest(response=response):
                session = UiSnapshotSession(self.session.adb_command, self.output)
                protocol = PrivateProtocol(session, self.clock)
                protocol.response_transform = lambda value: response
                with patch('ui_snapshot_session.subprocess.run', side_effect=protocol.run):
                    with self.assertRaises(RuntimeError):
                        session.capture('hierarchy-0001.xml')
                self.assertEqual([], protocol.xml_reads)
                self.assertEqual(response, (self.output / 'hierarchy-0001-session-response.json').read_bytes())

    def test_first_capture_ready_and_response_share_original_twenty_second_ceiling(self):
        self.protocol.ready_delay = 19
        self.protocol.response_transform = lambda response: None
        with self.assertRaisesRegex(RuntimeError, 'timed out'):
            self.session.capture('hierarchy-0001.xml')
        self.assertLessEqual(self.clock.now, 120.001)
        self.assertEqual([], self.protocol.xml_reads)
        self.popen.assert_called_once()
        self.assertTrue(all(0 < timeout <= 20 for _, timeout in self.protocol.calls))

    def test_caller_deadline_covers_first_connection_request_and_matching_response(self):
        self.protocol.ready_delay = 1.5
        self.protocol.response_transform = lambda response: None
        with self.assertRaisesRegex(RuntimeError, 'timed out'):
            self.session.capture('hierarchy-0001.xml', deadline=102)
        self.assertLessEqual(self.clock.now, 102.001)
        self.assertEqual([], self.protocol.xml_reads)
        self.popen.assert_called_once()
        self.assertTrue(all(0 < timeout <= 2 for _, timeout in self.protocol.calls))
        self.assertEqual(8000, self.protocol.requests[0]['root_wait_ms'])
        with self.assertRaises(RuntimeError):
            self.session.capture('hierarchy-0002.xml', deadline=110)
        self.popen.assert_called_once()  # A deadline failure cannot reconnect.

    def test_later_caller_deadline_cannot_expand_the_original_twenty_second_ceiling(self):
        self.protocol.response_transform = lambda response: None
        with self.assertRaisesRegex(RuntimeError, 'timed out'):
            self.session.capture('hierarchy-0001.xml', deadline=150)
        self.assertLessEqual(self.clock.now, 120.001)
        self.assertEqual([], self.protocol.xml_reads)
        self.assertTrue(all(0 < timeout <= 20 for _, timeout in self.protocol.calls))

    def test_expired_caller_deadline_never_starts_or_publishes_a_request(self):
        with self.assertRaisesRegex(RuntimeError, 'timed out before starting'):
            self.session.capture('hierarchy-0001.xml', deadline=100)
        self.popen.assert_not_called()
        self.assertEqual([], self.protocol.requests)
        self.assertEqual([], self.protocol.calls)
        self.assertEqual([], self.protocol.xml_reads)

    def test_matching_xml_that_finishes_after_caller_deadline_is_rejected(self):
        original = self.protocol.run
        def late_xml(command, **kwargs):
            result = original(command, **kwargs)
            if command[-1].endswith('.xml'):
                self.clock.now = 102.01
            return result
        self.adb.side_effect = late_xml
        with self.assertRaisesRegex(RuntimeError, 'timed out while reading matching XML'):
            self.session.capture('hierarchy-0001.xml', deadline=102)
        self.assertEqual(1, len(self.protocol.xml_reads))
        self.assertTrue((self.output / 'hierarchy-0001-session-response.json').is_file())
        self.assertIsNotNone(self.session.fatal_error)

    def test_direct_start_failure_poisoned_and_no_restart(self):
        self.protocol.files['ready.json'] = b'null'
        with self.assertRaises(RuntimeError):
            self.session.start(self.clock.now + 20)
        with self.assertRaises(RuntimeError):
            self.session.capture('hierarchy-0001.xml')
        self.popen.assert_called_once()
        self.assertEqual([], self.protocol.requests)

    def test_process_exit_before_response_cannot_read_old_xml(self):
        self.process.poll.return_value = 1
        with self.assertRaisesRegex(RuntimeError, 'exited'):
            self.session.capture('hierarchy-0001.xml')
        self.assertEqual([], self.protocol.xml_reads)
        self.assertEqual([], self.protocol.requests)

    def test_missing_matching_xml_is_fatal_and_cannot_restart(self):
        original_run = self.protocol.run
        def without_xml(command, **kwargs):
            if command[-1].endswith('.xml'):
                return subprocess.CompletedProcess(command, 1, b'', b'missing')
            return original_run(command, **kwargs)
        self.adb.side_effect = without_xml
        with self.assertRaisesRegex(RuntimeError, 'matching XML'):
            self.session.capture('hierarchy-0001.xml')
        with self.assertRaises(RuntimeError):
            self.session.capture('hierarchy-0002.xml')
        self.popen.assert_called_once()

    def test_invalid_close_ack_releases_only_owned_helper_and_still_fails(self):
        self.session.capture('hierarchy-0001.xml')
        self.protocol.files['closed.json'] = b'[]'
        with self.assertRaisesRegex(RuntimeError, 'cleanup failed'):
            self.session.close()
        self.assertIn(['adb', '-s', 'emulator-5554', 'shell', 'am', 'force-stop', HELPER],
                      [command for command, _ in self.protocol.calls])
        self.assertEqual(b'[]', (self.output / 'ui-snapshot-session-closed.json').read_bytes())
        self.assertTrue((self.output / 'ui-snapshot-session-instrumentation.txt').is_file())
        with self.assertRaises(RuntimeError):
            self.session.capture('hierarchy-0002.xml')

    def test_close_before_start_prevents_later_start_and_spawns_nothing(self):
        self.session.close()
        self.session.close()
        self.popen.assert_not_called()
        self.adb.assert_not_called()
        with self.assertRaisesRegex(RuntimeError, 'closed'):
            self.session.capture('hierarchy-0001.xml')

    def test_popen_failure_cleanup_is_safe_and_cannot_restart(self):
        self.popen.side_effect = OSError('missing adb')
        with self.assertRaisesRegex(OSError, 'missing adb'):
            self.session.capture('hierarchy-0001.xml')
        self.session.close()
        with self.assertRaises(RuntimeError):
            self.session.capture('hierarchy-0002.xml')
        self.popen.assert_called_once()

    def test_adb_timeout_is_fatal_and_reported(self):
        self.adb.side_effect = subprocess.TimeoutExpired(['adb'], 20)
        with self.assertRaisesRegex(RuntimeError, 'adb command timed out'):
            self.session.capture('hierarchy-0001.xml')
        self.popen.assert_called_once()
        self.assertIsNotNone(self.session.fatal_error)

    def test_command_journal_preserves_real_arguments_return_code_times_and_binary_output(self):
        stdout, stderr = b'\x00\xfforiginal stdout\r\n', b'\x80original stderr\x00'
        arguments = ['shell', 'run-as', HELPER, 'cat', f'{self.session.directory}/ready.json']
        def returned(command, **kwargs):
            self.assertFalse(list(self.output.glob('ui-snapshot-command-*')))
            self.assertEqual(100, self.clock.now)  # No pre-command evidence I/O.
            self.clock.now += .35
            return subprocess.CompletedProcess(command, 7, stdout, stderr)
        self.adb.side_effect = returned
        result = self.session._run(arguments, timeout=1.75)
        self.assertEqual((7, stdout, stderr), (result.returncode, result.stdout, result.stderr))
        journal = json.loads((self.output / 'ui-snapshot-commands.json').read_text())
        record = journal['commands'][0]
        self.assertEqual(self.session.nonce, journal['nonce'])
        self.assertEqual(self.session.adb_command + arguments, record['arguments'])
        self.assertEqual((1.75, 7, 'returned'),
                         (record['timeout_seconds'], record['returncode'], record['outcome']))
        self.assertEqual(100, record['started_monotonic_seconds'])
        self.assertAlmostEqual(100.35, record['ended_monotonic_seconds'])
        self.assertAlmostEqual(.35, record['elapsed_seconds'])
        self.assertGreater(record['started_unix_seconds'], 0)
        self.assertGreaterEqual(record['ended_unix_seconds'], record['started_unix_seconds'])
        self.assertEqual(stdout, (self.output / record['stdout']).read_bytes())
        self.assertEqual(stderr, (self.output / record['stderr']).read_bytes())

    def test_timeout_journal_keeps_partial_original_bytes_and_original_fatal_error(self):
        stdout, stderr = b'\xffpartial ready\x00', b'\x00\x80transport stderr'
        def timed_out(command, **kwargs):
            self.clock.now += kwargs['timeout']
            raise subprocess.TimeoutExpired(command, kwargs['timeout'], output=stdout, stderr=stderr)
        self.adb.side_effect = timed_out
        with self.assertRaisesRegex(RuntimeError, 'adb command timed out') as caught:
            self.session.capture('hierarchy-0001.xml', deadline=110)
        self.assertIsInstance(caught.exception.__cause__, subprocess.TimeoutExpired)
        record = self.session.commands[0]
        self.assertEqual(('timeout', None, 10),
                         (record['outcome'], record['returncode'], record['elapsed_seconds']))
        self.assertTrue(record['arguments'][-1].endswith('/ready.json'))
        self.assertEqual(stdout, (self.output / record['stdout']).read_bytes())
        self.assertEqual(stderr, (self.output / record['stderr']).read_bytes())
        self.assertEqual([], self.protocol.requests)
        with self.assertRaises(RuntimeError):
            self.session.capture('hierarchy-0002.xml', deadline=120)
        self.popen.assert_called_once()
        self.assertEqual(1, self.adb.call_count)

    def test_os_error_is_preserved_with_command_diagnostics(self):
        failure = OSError('actual missing adb executable')
        self.adb.side_effect = failure
        with self.assertRaises(OSError) as caught:
            self.session._run(['shell', 'run-as', HELPER, 'cat', 'ready.json'], timeout=2)
        self.assertIs(failure, caught.exception)
        self.assertEqual('os-error', self.session.commands[0]['outcome'])
        self.assertIn('actual missing adb executable', self.session.commands[0]['error'])

    def fail_diagnostic_writes(self):
        write = Path.write_bytes
        def only_diagnostics(path, content):
            if path.name.startswith('ui-snapshot-command') or path.name == 'ui-snapshot-session.json':
                raise OSError('diagnostic storage failure')
            return write(path, content)
        return patch.object(Path, 'write_bytes', only_diagnostics)

    def test_diagnostic_storage_failure_cannot_mask_the_original_timeout(self):
        self.adb.side_effect = subprocess.TimeoutExpired(['adb'], 10, output=b'raw partial')
        with self.fail_diagnostic_writes():
            with self.assertRaisesRegex(RuntimeError, 'adb command timed out') as caught:
                self.session.capture('hierarchy-0001.xml', deadline=110)
        self.assertIsInstance(caught.exception.__cause__, subprocess.TimeoutExpired)
        self.assertEqual('timeout', self.session.commands[0]['outcome'])
        self.assertTrue(self.session.diagnostic_errors)
        self.assertEqual('UiAutomation session adb command timed out', self.session.fatal_error)

    def test_diagnostic_storage_failure_cannot_become_a_new_success_condition(self):
        with self.fail_diagnostic_writes():
            metadata, xml = self.session.capture('hierarchy-0001.xml')
            self.session.close()
        self.assertEqual('ok', metadata['snapshot'])
        self.assertEqual(self.protocol.xml.decode(), xml)
        self.assertTrue(self.session.diagnostic_errors)
        self.popen.assert_called_once()
        self.process.communicate.assert_called_once_with(timeout=10)

    def test_native_ready_fields_and_final_instrumentation_remain_optional_evidence(self):
        ready = json.loads(self.protocol.files['ready.json'])
        ready['helper_diagnostics'] = {'helper_session_nonce': self.session.nonce, 'helper_pid': '2409',
                                     'helper_ready_write_started_uptime_ms': '65100'}
        self.protocol.files['ready.json'] = json.dumps(ready).encode()
        transcript = (f'INSTRUMENTATION_RESULT: helper_session_nonce={self.session.nonce}\n'
                      'INSTRUMENTATION_RESULT: helper_pid=2409\n'
                      'INSTRUMENTATION_RESULT: helper_ready_published_uptime_ms=65105\n'
                      'INSTRUMENTATION_CODE: -1\n').encode()
        self.process.communicate.return_value = (transcript, b'')
        metadata, xml = self.session.capture('hierarchy-0001.xml')
        self.assertEqual('ok', metadata['snapshot'])
        self.assertEqual(self.protocol.xml.decode(), xml)
        self.assertEqual(self.protocol.files['ready.json'], (self.output / 'ui-snapshot-session-ready.json').read_bytes())
        self.session.close()
        self.assertEqual(transcript, (self.output / 'ui-snapshot-session-instrumentation.txt').read_bytes())
        self.assertEqual(7, len(self.protocol.calls))  # Original ready/write/response/XML/stop/closed/rm only.

    def test_late_ready_native_diagnostics_cannot_publish_a_request_or_restart(self):
        ready = json.loads(self.protocol.files['ready.json'])
        ready['helper_diagnostics'] = {'helper_pid': '2409', 'helper_ready_write_started_uptime_ms': '65100'}
        self.protocol.files['ready.json'] = json.dumps(ready).encode()
        original_run = self.protocol.run
        def late_ready(command, **kwargs):
            result = original_run(command, **kwargs)
            self.clock.now = 110.01
            return result
        self.adb.side_effect = late_ready
        with self.assertRaisesRegex(RuntimeError, 'timed out while reading ready.json'):
            self.session.capture('hierarchy-0001.xml', deadline=110)
        self.assertEqual(self.protocol.files['ready.json'], (self.output / 'ui-snapshot-session-ready.json').read_bytes())
        self.assertEqual([], self.protocol.requests)
        self.assertFalse(any(event['event'] == 'ready' for event in self.session.events))
        with self.assertRaises(RuntimeError):
            self.session.capture('hierarchy-0002.xml', deadline=120)
        self.popen.assert_called_once()

    def test_post_command_diagnostic_io_still_consumes_the_original_caller_deadline(self):
        record = self.session._record_command
        def slow_evidence(*args):
            record(*args)
            self.clock.now += 3
        with patch.object(self.session, '_record_command', side_effect=slow_evidence):
            with self.assertRaisesRegex(RuntimeError, 'timed out while reading ready.json'):
                self.session.capture('hierarchy-0001.xml', deadline=102)
        self.assertAlmostEqual(.1, self.session.commands[0]['elapsed_seconds'])
        self.assertEqual(2, self.session.commands[0]['timeout_seconds'])
        self.assertEqual([], self.protocol.requests)
        self.popen.assert_called_once()


if __name__ == '__main__':
    unittest.main()
