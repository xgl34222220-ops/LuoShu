import unittest
import xml.etree.ElementTree as ET
from app_library_gate import candidate_notification_deny


class CandidateNotificationTests(unittest.TestCase):
    def tree(self, app='洛书·稳定重构测试', suffix='permission_deny_and_dont_ask_again_button'):
        root = ET.Element('hierarchy')
        ET.SubElement(root, 'node', {'package':'com.google.android.permissioncontroller','resource-id':'com.android.permissioncontroller:id/permission_message','text':f'Allow {app} to send you notifications?'})
        ET.SubElement(root, 'node', {'package':'com.google.android.permissioncontroller','resource-id':'com.android.permissioncontroller:id/'+suffix,'text':'Don’t allow','enabled':'true'})
        return root
    def test_observed_deny_variants(self):
        for suffix in ('permission_deny_button','permission_deny_and_dont_ask_again_button'):
            self.assertIsNotNone(candidate_notification_deny(self.tree(suffix=suffix)))
    def test_other_package_or_allow_rejected(self):
        self.assertIsNone(candidate_notification_deny(self.tree(app='洛书')))
        self.assertIsNone(candidate_notification_deny(self.tree(suffix='permission_allow_button')))
