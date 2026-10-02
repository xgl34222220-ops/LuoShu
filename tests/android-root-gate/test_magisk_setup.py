import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).parent))
from magisk_avd import reviewed_setup_prompt


class OfficialSetupPromptTests(unittest.TestCase):
    def test_expected_official_setup_and_reboot(self):
        self.assertTrue(reviewed_setup_prompt('Requires additional setup Your device needs additional setup for Magisk to work properly. Do you want to proceed and reboot? OK Cancel'))

    def test_reflash_or_unrelated_download_is_not_accepted(self):
        self.assertFalse(reviewed_setup_prompt('Requires additional setup Your device needs reflash Magisk to work properly. Please reinstall Magisk within app. OK'))
        self.assertFalse(reviewed_setup_prompt('Requires additional setup Download a component and reboot? OK'))
