import importlib.util
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).parent))
from candidate_gate import app_launch_result

PACKAGE = 'io.github.xgl34222220.luoshu.stabletest'


class AppGateTests(unittest.TestCase):
    def test_am_success_does_not_mask_crash(self):
        log = 'FATAL EXCEPTION: main\nProcess: ' + PACKAGE + ', PID: 123\nNullPointerException'
        self.assertEqual(app_launch_result(PACKAGE, 'Status: ok', log, PACKAGE, False)['result'], 'FAIL')

    def test_system_anr_blocks_ui_gate(self):
        self.assertEqual(app_launch_result(PACKAGE, 'Status: ok', '', "System UI isn't responding", True)['result'], 'BLOCKED')

    def test_permission_modal_is_not_app_readiness(self):
        self.assertEqual(app_launch_result(PACKAGE, 'Status: ok', '', 'permissioncontroller', True)['result'], 'BLOCKED')

    def test_visible_alive_app_only_passes_launch(self):
        self.assertEqual(app_launch_result(PACKAGE, 'Status: ok', '', PACKAGE, True)['result'], 'PASS')
