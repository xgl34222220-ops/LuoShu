import sys
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).parent))
from adb_ui import dump_ui


class FreshHierarchyTests(unittest.TestCase):
    def test_exit_zero_error_never_reads_stale_file(self):
        calls = []
        def run(args, **kwargs):
            calls.append(args)
            if len(calls) == 1:
                return subprocess.CompletedProcess(args, 0, '', 'ERROR: null root node returned by UiTestAutomationBridge.')
            if args[-1].startswith('uiautomator dump '):
                path = args[-1].split()[-1]
                return subprocess.CompletedProcess(args, 0, 'UI hierchary dumped to: ' + path, '')
            if args[-1].startswith('cat '):
                return subprocess.CompletedProcess(args, 0, '<hierarchy><node/></hierarchy>', '')
            return subprocess.CompletedProcess(args, 0, '', '')
        with patch('adb_ui.subprocess.run', side_effect=run), patch('adb_ui.time.sleep'):
            self.assertEqual(dump_ui(['adb'], '/data/local/tmp/test'), '<hierarchy><node/></hierarchy>')
        self.assertIn('uiautomator dump ', calls[1][-1])
        self.assertNotEqual(calls[0][-1], calls[1][-1])
        self.assertEqual(sum(c[-1].startswith('cat ') for c in calls), 1)
