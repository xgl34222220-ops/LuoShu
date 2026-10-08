#!/usr/bin/env python3
"""Exercise transport identities/deadlines, not an invented accessibility tree."""
import json
import shlex
import shutil
import subprocess
import tempfile
import time
import unittest
import sys
from pathlib import Path
from unittest.mock import Mock, patch

from ui_snapshot_session import HELPER, ROOT_WAIT_MS, UiSnapshotSession

REAL_POPEN = subprocess.Popen

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
        session._protocol_fixture = self
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

    def wait_publication(self, basename, deadline):
        # These existing private-file tests model publication scheduling only.
        # The real-pipe class below exercises the production reader and waiter.
        while True:
            if self.clock.now >= deadline:
                raise RuntimeError(f'UiAutomation session timed out waiting for {basename}')
            if self.session.process.poll() is not None:
                raise RuntimeError('UiAutomation session exited before its matching response')
            if basename in self.files and (basename != 'ready.json' or self.clock.now >= 100 + self.ready_delay):
                return
            self.clock.sleep(min(.1, deadline - self.clock.now))

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
        self.process.wait.return_value = 0
        self.enterContext(patch.object(UiSnapshotSession, '_start_readers'))
        self.enterContext(patch.object(UiSnapshotSession, '_wait_publication', autospec=True,
                                      side_effect=lambda current, basename, deadline:
                                      current._protocol_fixture.wait_publication(basename, deadline)))
        self.enterContext(patch.object(UiSnapshotSession, '_finish_readers',
                                      side_effect=lambda deadline: self.finish_reader_fixture(deadline)))
        self.popen = self.enterContext(patch('ui_snapshot_session.subprocess.Popen', return_value=self.process))
        self.adb = self.enterContext(patch('ui_snapshot_session.subprocess.run', side_effect=self.protocol.run))
        self.enterContext(patch('ui_snapshot_session.time.monotonic', side_effect=self.clock.monotonic))
        self.enterContext(patch('ui_snapshot_session.time.sleep', side_effect=self.clock.sleep))

    def finish_reader_fixture(self, deadline):
        self.process.wait(timeout=deadline - self.clock.now)
        return self.process.communicate.return_value

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
        self.process.wait.assert_called_once_with(timeout=10)
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
        self.process.wait.assert_called_once_with(timeout=10)

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

    def test_last_failed_native_snapshot_diagnostic_keeps_normal_session_close(self):
        failure = {'snapshot': 'failed', 'error': 'No active accessibility window', 'wait_ms': '8000'}
        self.protocol.response_transform = lambda response: {**response, 'code': 0, 'result': failure}
        metadata, xml = self.session.capture('hierarchy-0001.xml')
        request = self.protocol.requests[-1]
        transcript = (f'INSTRUMENTATION_RESULT: helper_session_nonce={self.session.nonce}\n'
                      f'INSTRUMENTATION_RESULT: helper_last_request_id={request["request_id"]}\n'
                      'INSTRUMENTATION_RESULT: helper_last_request_status=response-published\n'
                      'INSTRUMENTATION_RESULT: helper_last_snapshot_status=failed\n'
                      'INSTRUMENTATION_RESULT: helper_last_snapshot_error=No active accessibility window\n'
                      'INSTRUMENTATION_RESULT: helper_last_response_code=0\n'
                      'INSTRUMENTATION_RESULT: session=finished\n'
                      f'INSTRUMENTATION_RESULT: session_nonce={self.session.nonce}\n'
                      'INSTRUMENTATION_CODE: -1\n').encode()
        self.process.communicate.return_value = (transcript, b'')
        self.session.close()
        self.assertEqual(failure, metadata)
        self.assertIsNone(xml)
        self.assertIsNone(self.session.fatal_error)
        self.assertEqual('closed', self.session.events[-1]['event'])
        self.assertEqual(transcript, (self.output / 'ui-snapshot-session-instrumentation.txt').read_bytes())
        self.assertEqual(6, len(self.protocol.calls))  # No XML read; original stop/closed/rm only.
        self.assertFalse(any('force-stop' in command for command, _ in self.protocol.calls))
        self.popen.assert_called_once()

    def test_final_late_native_success_cannot_salvage_host_timeout_or_restart(self):
        self.protocol.response_transform = lambda response: None
        with self.assertRaisesRegex(RuntimeError, 'timed out'):
            self.session.capture('hierarchy-0001.xml', deadline=102)
        original_error = self.session.fatal_error
        request = self.protocol.requests[-1]
        # The matching response exists only after the original host deadline.
        self.protocol.files['response-' + request['request_id'] + '.json'] = json.dumps(
            {**request, 'code': -1, 'result': {'snapshot': 'ok', 'filename': request['filename']}}).encode()
        transcript = (f'INSTRUMENTATION_RESULT: helper_last_request_id={request["request_id"]}\n'
                      'INSTRUMENTATION_RESULT: helper_last_request_status=response-published\n'
                      'INSTRUMENTATION_RESULT: helper_last_snapshot_status=ok\n'
                      'INSTRUMENTATION_RESULT: helper_last_response_published_uptime_ms=73100\n'
                      'INSTRUMENTATION_CODE: -1\n').encode()
        self.process.communicate.return_value = (transcript, b'')
        self.session.close()
        self.assertEqual(original_error, self.session.fatal_error)
        self.assertEqual([], self.protocol.xml_reads)
        self.assertEqual('closed', self.session.events[-1]['event'])
        self.assertEqual(transcript, (self.output / 'ui-snapshot-session-instrumentation.txt').read_bytes())
        with self.assertRaises(RuntimeError):
            self.session.capture('hierarchy-0002.xml', deadline=110)
        self.popen.assert_called_once()
        self.assertEqual(1, len(self.protocol.requests))

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


class PublicationPipeTest(unittest.TestCase):
    """Real child-process pipes test the production framing/drain/deadline code."""

    producer = r'''
import json, os, sys, time
from pathlib import Path
directory=Path(sys.argv[1]); nonce=sys.argv[2]
config=json.loads((directory/'producer.json').read_text()); mode=config['mode']
stop=directory/'stop'; request=directory/'request.json'
def emit(stream,raw,fragment=False):
    with (directory/('producer-'+stream+'.bin')).open('ab') as trace:
        while raw:
            piece=raw[:17] if fragment else raw
            count=os.write(1 if stream=='stdout' else 2,piece)
            trace.write(piece[:count]); trace.flush(); raw=raw[count:]
            if fragment: time.sleep(.001)
def frame(basename):
    raw=json.dumps({'protocol':1,'nonce':nonce,'basename':basename},separators=(',',':')).encode()
    return b'INSTRUMENTATION_STATUS: luoshu_snapshot_published='+raw+b'\nINSTRUMENTATION_STATUS_CODE: 1\n'
emit('stderr',b'\x00\xff'+(b'pipe-pressure-stderr\n'*8192 if mode=='high-stderr' else b'initial-stderr\n'))
emit('stdout',b'\xffraw-start\n'+(b'x'*12000+b'\n' if mode=='high-stderr' else b''))
ready=frame('ready.json')
if mode=='bad': ready=bytes.fromhex(config['frame_hex'])
if mode=='duplicate': ready+=ready
if mode=='interleaved': ready=ready.replace(b'INSTRUMENTATION_STATUS_CODE:',b'INSTRUMENTATION_RESULT: other=value\nINSTRUMENTATION_STATUS_CODE:')
if mode=='interleaved-long': ready=ready.replace(b'INSTRUMENTATION_STATUS_CODE:',b'x'*12000+b'\nINSTRUMENTATION_STATUS_CODE:')
if mode=='missing': ready=b'luoshu_snapshot_published={"protocol":1}\n'
if mode=='partial-line-eof': ready=ready[:90]
if mode=='fields-eof': ready=ready.split(b'INSTRUMENTATION_STATUS_CODE:')[0]
if mode=='late': time.sleep(.2)
emit('stdout',ready,mode=='high-stderr')
if mode in ('eof','partial-line-eof','fields-eof'): sys.exit(0)
until=time.monotonic()+5
while not request.exists() and not stop.exists() and time.monotonic()<until: time.sleep(.005)
if request.exists():
    value=json.loads(request.read_text()); response=frame('response-'+value['request_id']+'.json')
    if mode=='response-duplicate': response+=response
    emit('stdout',response,mode=='high-stderr')
    if mode=='after-xml':
        while not (directory/'xml-read').exists() and not stop.exists() and time.monotonic()<until: time.sleep(.005)
        emit('stdout',frame('ready.json'))
while not stop.exists() and time.monotonic()<until: time.sleep(.005)
if mode=='close-extra': emit('stdout',frame('response-'+'0'*32+'.json'))
emit('stdout',b'INSTRUMENTATION_RESULT: session=finished\nINSTRUMENTATION_CODE: -1\n')
emit('stderr',b'\x80raw-final-stderr\n')
'''

    def make_session(self, mode, *, frame=None):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name)
        session = UiSnapshotSession(['adb', '-s', 'emulator-5554'], directory)
        protocol = PrivateProtocol(session, Clock())
        config = {'mode': mode}
        if frame is not None:
            config['frame_hex'] = frame(session.nonce).hex()
        (directory / 'producer.json').write_text(json.dumps(config))
        real_popen = REAL_POPEN
        processes = []

        def launch(command, **kwargs):
            self.assertIn('instrument', command)
            process = real_popen([sys.executable, '-c', self.producer, str(directory), session.nonce], **kwargs)
            processes.append(process)
            return process

        def transport(command, **kwargs):
            result = protocol.run(command, **kwargs)
            if protocol.requests:
                (directory / 'request.json').write_text(json.dumps(protocol.requests[-1]))
            if command[-1].endswith('.xml') and mode == 'after-xml':
                (directory / 'xml-read').touch()
                until = time.monotonic() + 1
                while session._pipe_error is None and time.monotonic() < until:
                    time.sleep(.005)
            if command[-1].endswith("stop.json'"):
                (directory / 'stop').touch()
            return result

        self.enterContext(patch('ui_snapshot_session.subprocess.Popen', side_effect=launch))
        self.enterContext(patch('ui_snapshot_session.subprocess.run', side_effect=transport))

        def cleanup():
            (directory / 'stop').touch()
            for process in processes:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=3)
            for thread in session._pipe_threads:
                thread.join(timeout=3)
        self.addCleanup(cleanup)
        return session, protocol, directory, processes

    @staticmethod
    def frame(nonce, *, notice=None, code=b'1'):
        notice = notice if notice is not None else {'protocol': 1, 'nonce': nonce, 'basename': 'ready.json'}
        raw = notice if isinstance(notice, bytes) else json.dumps(notice).encode()
        return b'INSTRUMENTATION_STATUS: luoshu_snapshot_published=' + raw + b'\nINSTRUMENTATION_STATUS_CODE: ' + code + b'\n'

    def assert_raw_preserved(self, directory):
        stdout = (directory / 'producer-stdout.bin').read_bytes()
        stderr = (directory / 'producer-stderr.bin').read_bytes()
        self.assertEqual(stdout, (directory / 'ui-snapshot-session-instrumentation-stdout.bin').read_bytes())
        self.assertEqual(stderr, (directory / 'ui-snapshot-session-instrumentation-stderr.bin').read_bytes())
        self.assertEqual(stdout + stderr, (directory / 'ui-snapshot-session-instrumentation.txt').read_bytes())

    def test_fragmented_notices_high_stderr_and_long_unrelated_stdout_keep_one_read_per_file(self):
        session, protocol, directory, processes = self.make_session('high-stderr')
        metadata, xml = session.capture('hierarchy-0001.xml', deadline=time.monotonic() + 3)
        self.assertEqual('ok', metadata['snapshot'])
        self.assertEqual(protocol.xml.decode(), xml)
        session.close()
        json_reads = [command[-1] for command, _ in protocol.calls
                      if command[-1].endswith('.json') and 'response-' in command[-1] or command[-1].endswith('/ready.json')]
        self.assertEqual(2, len(json_reads))
        self.assertEqual(1, len(processes))
        self.assertEqual('closed', session.events[-1]['event'])
        self.assertTrue(processes[0].stdout.closed and processes[0].stderr.closed)
        self.assert_raw_preserved(directory)
        self.assertGreater((directory / 'producer-stderr.bin').stat().st_size, 128 * 1024)
        self.assertFalse(any('force-stop' in command for command, _ in protocol.calls))

    def test_missing_notice_never_reads_existing_ready_json_or_reconnects(self):
        session, protocol, directory, processes = self.make_session('missing')
        started = time.monotonic()
        with self.assertRaisesRegex(RuntimeError, 'timed out'):
            session.capture('hierarchy-0001.xml', deadline=started + .15)
        self.assertLess(time.monotonic() - started, .35)
        self.assertEqual([], protocol.calls)
        self.assertEqual([], protocol.requests)
        session.close()
        self.assert_raw_preserved(directory)
        with self.assertRaises(RuntimeError):
            session.capture('hierarchy-0002.xml')
        self.assertEqual(1, len(processes))

    def test_notice_after_caller_deadline_cannot_salvage_timeout_or_normal_close(self):
        session, protocol, directory, processes = self.make_session('late')
        with self.assertRaisesRegex(RuntimeError, 'timed out'):
            session.capture('hierarchy-0001.xml', deadline=time.monotonic() + .06)
        original = session.fatal_error
        self.assertEqual([], protocol.calls)
        with self.assertRaisesRegex(RuntimeError, 'cleanup failed'):
            session.close()
        self.assertEqual(original, session.fatal_error)
        self.assert_raw_preserved(directory)
        self.assertEqual(1, len(processes))

    def test_eof_before_matching_response_is_fatal_and_cannot_read_xml(self):
        session, protocol, directory, _ = self.make_session('eof')
        with self.assertRaisesRegex(RuntimeError, 'exited'):
            session.capture('hierarchy-0001.xml', deadline=time.monotonic() + 1)
        self.assertEqual([], protocol.xml_reads)
        with self.assertRaisesRegex(RuntimeError, 'cleanup failed'):
            session.close()
        self.assert_raw_preserved(directory)

    def test_bad_notices_retain_later_final_code_and_raw_stderr_without_json_fallback(self):
        cases = {
            'wrong-nonce': lambda nonce: self.frame(nonce, notice={'protocol': 1, 'nonce': '0' * 32, 'basename': 'ready.json'}),
            'boolean-protocol': lambda nonce: self.frame(nonce, notice={'protocol': True, 'nonce': nonce, 'basename': 'ready.json'}),
            'bad-basename': lambda nonce: self.frame(nonce, notice={'protocol': 1, 'nonce': nonce, 'basename': '../old.json'}),
            'extra-field': lambda nonce: self.frame(nonce, notice={'protocol': 1, 'nonce': nonce, 'basename': 'ready.json', 'extra': 1}),
            'malformed-json': lambda nonce: self.frame(nonce, notice=b'{broken'),
            'duplicate-json-key': lambda nonce: self.frame(nonce, notice=(f'{{"protocol":1,"protocol":1,"nonce":"{nonce}","basename":"ready.json"}}').encode()),
            'oversized-notice': lambda nonce: self.frame(nonce, notice=b' ' * 513),
            'wrong-status-code': lambda nonce: self.frame(nonce, code=b'0'),
            'partial-record': lambda nonce: self.frame(nonce).split(b'\n')[0] + b'\n',
        }
        for name, frame in cases.items():
            with self.subTest(name=name):
                session, protocol, directory, _ = self.make_session('bad', frame=frame)
                with self.assertRaises(RuntimeError):
                    session.capture('hierarchy-0001.xml', deadline=time.monotonic() + 1)
                self.assertEqual([], protocol.calls)
                self.assertEqual([], protocol.xml_reads)
                with self.assertRaisesRegex(RuntimeError, 'cleanup failed'):
                    session.close()
                self.assert_raw_preserved(directory)
                self.assertIn(b'INSTRUMENTATION_CODE: -1\n', (directory / 'producer-stdout.bin').read_bytes())

    def test_physical_eof_with_partial_notice_preserves_original_partial_bytes(self):
        for mode in ('partial-line-eof', 'fields-eof'):
            with self.subTest(mode=mode):
                session, protocol, directory, _ = self.make_session(mode)
                with self.assertRaises(RuntimeError):
                    session.capture('hierarchy-0001.xml', deadline=time.monotonic() + 1)
                self.assertEqual([], protocol.calls)
                self.assertEqual([], protocol.xml_reads)
                with self.assertRaisesRegex(RuntimeError, 'cleanup failed'):
                    session.close()
                self.assertIn('mid-record', session._pipe_error)
                self.assert_raw_preserved(directory)

    def test_duplicate_and_interleaved_frames_cannot_publish_a_ready_token(self):
        for mode in ('duplicate', 'interleaved', 'interleaved-long'):
            with self.subTest(mode=mode):
                session, protocol, directory, _ = self.make_session(mode)
                with self.assertRaisesRegex(RuntimeError, 'duplicate|interrupted'):
                    session.capture('hierarchy-0001.xml', deadline=time.monotonic() + 1)
                self.assertEqual([], protocol.calls)
                with self.assertRaises(RuntimeError):
                    session.close()
                self.assert_raw_preserved(directory)

    def test_duplicate_response_notice_is_fatal_before_xml_and_retains_final_transcript(self):
        session, protocol, directory, _ = self.make_session('response-duplicate')
        with self.assertRaisesRegex(RuntimeError, 'duplicate'):
            session.capture('hierarchy-0001.xml', deadline=time.monotonic() + 1)
        self.assertEqual([], protocol.xml_reads)
        with self.assertRaises(RuntimeError):
            session.close()
        self.assert_raw_preserved(directory)

    def test_bad_notice_arriving_during_xml_read_cannot_complete_capture(self):
        session, protocol, directory, _ = self.make_session('after-xml')
        with self.assertRaisesRegex(RuntimeError, 'duplicate'):
            session.capture('hierarchy-0001.xml', deadline=time.monotonic() + 1)
        self.assertEqual(1, len(protocol.xml_reads))
        with self.assertRaises(RuntimeError):
            session.close()
        self.assert_raw_preserved(directory)

    def test_extra_notice_at_normal_close_fails_and_preserves_all_original_bytes(self):
        session, protocol, directory, _ = self.make_session('close-extra')
        session.capture('hierarchy-0001.xml', deadline=time.monotonic() + 1)
        with self.assertRaisesRegex(RuntimeError, 'unconsumed'):
            session.close()
        self.assert_raw_preserved(directory)


class NativeLastRequestDiagnosticsTest(unittest.TestCase):
    def test_production_java_last_request_diagnostics_and_finish_code(self):
        java = shutil.which('java')
        if java is None:
            self.skipTest('Production Java diagnostic regression requires the host JDK')
        source = (Path(__file__).parent / 'ui_snapshot' / 'SnapshotInstrumentation.java').read_text()

        def method(signature):
            start = source.index(signature)
            return source[start:source.index('\n    }', start) + len('\n    }')]

        methods = '\n'.join(method(signature) for signature in (
            '    private static void lastDiagnostic(',
            '    private static void lastDiagnosticTime(',
            '    private static void acceptRequestDiagnostics(',
            '    private static void rootQueryStarted(',
            '    private static void rootQueryReturned(',
            '    private static void snapshotDiagnostics(',
            '    public void onStart()',
        ))
        harness = r'''
import java.io.File;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Set;
public class NativeLastRequestDiagnosticsHarness {
    static class Bundle {
        final HashMap<String,String> values = new HashMap<>();
        void putString(String key,String value) { values.put(key,value); }
        String getString(String key) { return values.get(key); }
        String getString(String key,String fallback) { return values.getOrDefault(key,fallback); }
        void putAll(Bundle other) { values.putAll(other.values); }
        Set<String> keySet() { return values.keySet(); }
        void remove(String key) { values.remove(key); }
        boolean containsKey(String key) { return values.containsKey(key); }
    }
    static class SystemClock {
        static long now;
        static long uptimeMillis() { return now; }
    }
    static class Activity { static final int RESULT_OK=-1, RESULT_CANCELED=0; }
    static class Context { File getFilesDir() { return new File("unused"); } }
    Bundle arguments = new Bundle();
    Bundle finished;
    int finishCode=123;
    boolean failSession;
    void finish(int code,Bundle result) { finishCode=code; finished=result; }
    Context getContext() { throw new AssertionError("Must use the session path"); }
    Object connectAutomation(Bundle diagnostics) { throw new AssertionError("No automation in this method regression"); }
    Bundle snapshot(Object automation,String filename,File directory,Bundle diagnostics) { throw new AssertionError("No snapshot in this method regression"); }
    static Bundle failedSnapshot() {
        Bundle result=new Bundle();
        result.putString("snapshot","failed");
        char[] error=new char[4096]; java.util.Arrays.fill(error,'x');
        result.putString("error",new String(error));
        result.putString("wait_ms","8000"); result.putString("attempts","5");
        result.putString("last_root_visible_child_count","0");
        result.putString("root_observations","must not be copied");
        result.putString("window_counts","must not be copied");
        result.putString("filename","must not be copied");
        return result;
    }
    Bundle runSession(String nonce,Bundle diagnostics) throws Exception {
        if(failSession) throw new IllegalStateException("original session failure");
        acceptRequestDiagnostics(diagnostics,"new-request","hierarchy-0002.xml");
        snapshotDiagnostics(diagnostics,failedSnapshot());
        Bundle result=new Bundle(); result.putString("session","finished"); result.putString("session_nonce",nonce);
        return result;
    }
    static void require(boolean ok,String message) { if(!ok) throw new AssertionError(message); }
    public static void main(String[] args) {
        Bundle diagnostics=new Bundle();
        diagnostics.putString("helper_ready_published_uptime_ms","100");
        diagnostics.putString("helper_last_request_id","old-request");
        diagnostics.putString("helper_last_export_finished_uptime_ms","200");
        diagnostics.putString("helper_last_snapshot_status","ok");
        SystemClock.now=700;
        acceptRequestDiagnostics(diagnostics,"new-request","hierarchy-0002.xml");
        require("new-request".equals(diagnostics.getString("helper_last_request_id")),"request identity not replaced");
        require("hierarchy-0002.xml".equals(diagnostics.getString("helper_last_request_filename")),"filename missing");
        require("700".equals(diagnostics.getString("helper_last_request_accepted_uptime_ms")),"accept time changed clocks");
        require("accepted".equals(diagnostics.getString("helper_last_request_status")),"missing accepted status");
        require(!diagnostics.containsKey("helper_last_export_finished_uptime_ms") &&
                !diagnostics.containsKey("helper_last_snapshot_status"),"stale last-request result or time retained");
        require("100".equals(diagnostics.getString("helper_ready_published_uptime_ms")),"connection evidence removed");
        diagnostics.putString("helper_last_root_query_returned_uptime_ms","300");
        SystemClock.now=710; rootQueryStarted(diagnostics,"getRootInActiveWindow");
        require(!diagnostics.containsKey("helper_last_root_query_returned_uptime_ms"),"old query return mixed with new query");
        require("started".equals(diagnostics.getString("helper_last_root_query_status")),"query entered status missing");
        SystemClock.now=713; rootQueryReturned(diagnostics);
        require("710".equals(diagnostics.getString("helper_last_root_query_started_uptime_ms")) &&
                "713".equals(diagnostics.getString("helper_last_root_query_returned_uptime_ms")),"query times not native uptime");
        require("returned".equals(diagnostics.getString("helper_last_root_query_status")),"query return status missing");
        snapshotDiagnostics(diagnostics,failedSnapshot());
        require("failed".equals(diagnostics.getString("helper_last_snapshot_status")),"failed status lost");
        require(diagnostics.getString("helper_last_snapshot_error").length()==1024,"unbounded error summary");
        require("8000".equals(diagnostics.getString("helper_last_snapshot_wait_ms")),"scalar summary lost");
        require(!diagnostics.containsKey("snapshot") && !diagnostics.containsKey("error") &&
                !diagnostics.containsKey("helper_last_snapshot_root_observations") &&
                !diagnostics.containsKey("helper_last_snapshot_window_counts") &&
                !diagnostics.containsKey("helper_last_snapshot_filename"),"full or unprefixed snapshot result leaked");
        lastDiagnostic(null,"request_status","ignored"); lastDiagnosticTime(null,"snapshot_started");
        rootQueryStarted(null,"ignored"); rootQueryReturned(null);
        NativeLastRequestDiagnosticsHarness normal=new NativeLastRequestDiagnosticsHarness();
        normal.arguments.putString("session_nonce","test-nonce"); normal.onStart();
        require(normal.finishCode==-1 && "finished".equals(normal.finished.getString("session")),"last failed snapshot changed normal finish code");
        require("failed".equals(normal.finished.getString("helper_last_snapshot_status")) &&
                !normal.finished.containsKey("snapshot") && !normal.finished.containsKey("error"),"final diagnostic merge altered session result");
        NativeLastRequestDiagnosticsHarness broken=new NativeLastRequestDiagnosticsHarness();
        broken.arguments.putString("session_nonce","test-nonce"); broken.failSession=true; broken.onStart();
        require(broken.finishCode==0 && "failed".equals(broken.finished.getString("snapshot")),"original session failure no longer fails");
        System.out.println("Passed production Java last-request diagnostics and finish-code regression");
    }
''' + methods + '\n}\n'
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            file = directory / 'NativeLastRequestDiagnosticsHarness.java'
            file.write_text(harness)
            compiled = subprocess.run([java, '--module', 'jdk.compiler/com.sun.tools.javac.Main',
                                       '-d', str(directory), str(file)], capture_output=True, timeout=30)
            self.assertEqual(0, compiled.returncode, compiled.stderr.decode())
            exercised = subprocess.run([java, '-cp', str(directory), 'NativeLastRequestDiagnosticsHarness'],
                                       capture_output=True, timeout=10)
            self.assertEqual(0, exercised.returncode, exercised.stderr.decode())
            self.assertIn('Passed production Java last-request diagnostics and finish-code regression', exercised.stdout.decode())


if __name__ == '__main__':
    unittest.main()
