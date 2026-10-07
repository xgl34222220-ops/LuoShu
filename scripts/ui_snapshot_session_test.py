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


if __name__ == '__main__':
    unittest.main()
