#!/usr/bin/env python3
"""Host tests for the screenshot harness; these do not claim emulator coverage."""

import unittest
import xml.etree.ElementTree as ET

from android_ui_smoke import center, crash_reason, page_ready, tab_target


PACKAGE = "io.github.xgl34222220.luoshu.debug"


class UiSmokeHarnessTest(unittest.TestCase):
    def hierarchy(self, selected="true"):
        return ET.fromstring(f'''<hierarchy>
          <node package="{PACKAGE}" text="字体库" clickable="true" enabled="true" bounds="[20,300][400,400]" />
          <node package="{PACKAGE}" text="搜索你的字体" clickable="false" bounds="[20,80][400,140]" />
          <node package="{PACKAGE}" clickable="true" enabled="true" selected="{selected}" bounds="[220,900][400,990]">
            <node package="{PACKAGE}" text="字体库" clickable="false" bounds="[230,940][390,970]" />
          </node>
        </hierarchy>''')

    def test_uses_clickable_parent_and_bottom_tab_instead_of_home_card(self):
        target = tab_target(self.hierarchy(), "字体库", PACKAGE)
        self.assertEqual((310, 945), center(target))

    def test_requires_selected_tab_and_actual_page_content(self):
        self.assertTrue(page_ready(self.hierarchy(), "字体库", "搜索你的字体", PACKAGE))
        self.assertFalse(page_ready(self.hierarchy("false"), "字体库", "搜索你的字体", PACKAGE))
        self.assertFalse(page_ready(self.hierarchy(), "字体库", "字体组合", PACKAGE))

    def test_ignores_other_packages_crashes_but_rejects_our_java_fatal(self):
        unrelated = "AndroidRuntime: FATAL EXCEPTION: main\nAndroidRuntime: Process: com.android.other, PID: 32"
        self.assertIsNone(crash_reason(unrelated, PACKAGE))
        self.assertIn("FATAL", crash_reason(unrelated.replace("com.android.other", PACKAGE), PACKAGE))

    def test_rejects_native_crash_and_anr(self):
        self.assertIn("native", crash_reason(f"DEBUG: pid 123 >>> {PACKAGE} <<<", PACKAGE))
        self.assertIn("ANR", crash_reason(f"ActivityManager: ANR in {PACKAGE} (MainActivity)", PACKAGE))

    def test_rejects_invisible_or_disabled_navigation(self):
        root = self.hierarchy()
        for node in root.iter("node"):
            node.set("enabled", "false")
        with self.assertRaisesRegex(ValueError, "not found"):
            tab_target(root, "字体库", PACKAGE)


if __name__ == "__main__":
    unittest.main()
