import sys
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).parent))
from adb_utils import ensure_root


def answer(code=0, stdout='', stderr=''):
    return subprocess.CompletedProcess([], code, stdout, stderr)


class RootHandshakeTests(unittest.TestCase):
    def test_already_root_never_restarts_adbd(self):
        with patch('adb_utils.subprocess.run', return_value=answer(stdout='0\n')) as run:
            ensure_root(['adb', '-s', 'emulator-5554'])
            self.assertEqual(run.call_count, 1)

    def test_closed_transport_rechecks_real_uid(self):
        replies = [answer(1, stderr='closed'), answer(1, stderr='unable to connect for root: closed'), answer(), answer(stdout='0\n')]
        with patch('adb_utils.subprocess.run', side_effect=replies), patch('adb_utils.time.sleep'):
            ensure_root(['adb', '-s', 'emulator-5554'])

    def test_production_denial_never_retried(self):
        with patch('adb_utils.subprocess.run', side_effect=[answer(stdout='2000\n'), answer(1, stderr='adbd cannot run as root in production builds')]) as run:
            with self.assertRaisesRegex(RuntimeError, 'denied'):
                ensure_root(['adb', '-s', 'emulator-5554'])
            self.assertEqual(run.call_count, 2)
