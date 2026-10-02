import unittest
import xml.etree.ElementTree as ET
from magisk_avd import system_ui_anr_wait


class SystemAnrWaitTests(unittest.TestCase):
    def tree(self, title="System UI isn't responding", button='Wait'):
        tree = ET.Element('hierarchy')
        ET.SubElement(tree, 'node', {'package': 'android', 'resource-id': 'android:id/alertTitle', 'text': title})
        ET.SubElement(tree, 'node', {'package': 'android', 'resource-id': 'android:id/aerr_wait', 'text': button, 'enabled': 'true', 'bounds': '[0,0][100,100]'})
        return tree

    def test_exact_system_ui_wait(self):
        self.assertIsNotNone(system_ui_anr_wait(self.tree()))

    def test_target_app_anr_never_accepted(self):
        self.assertIsNone(system_ui_anr_wait(self.tree("洛书 isn't responding")))

    def test_close_never_accepted(self):
        self.assertIsNone(system_ui_anr_wait(self.tree(button='Close app')))

    def test_duplicate_wait_rejected(self):
        tree = self.tree()
        ET.SubElement(tree, 'node', dict(list(tree)[-1].attrib))
        self.assertIsNone(system_ui_anr_wait(tree))
