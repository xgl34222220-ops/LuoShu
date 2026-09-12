#!/usr/bin/env python3
"""Host tests for the screenshot harness; these do not claim emulator coverage."""

import unittest
import xml.etree.ElementTree as ET

from android_ui_smoke import center, crash_reason, page_ready, tab_target


PACKAGE = "io.github.xgl34222220.luoshu.debug"


class UiSmokeHarnessTest(unittest.TestCase):
    def hierarchy(self, selected="首页"):
        # Reduced from the API 36 CI XML: the selected tab is focusable but not
        # clickable; the three unselected sibling tabs are clickable. Preserve
        # the actual bounds and the unrelated clickable font-library home card.
        return ET.fromstring(f'''<hierarchy>
          <node package="{PACKAGE}" bounds="[0,144][1440,3120]">
            <node package="{PACKAGE}" text="当前字体" clickable="false" bounds="[70,640][360,720]" />
            <node package="{PACKAGE}" clickable="true" enabled="true" focusable="true" bounds="[70,2179][699,2661]">
              <node package="{PACKAGE}" text="字体库" clickable="false" bounds="[133,2438][310,2523]" />
            </node>
            <node package="{PACKAGE}" bounds="[91,2763][1349,2973]">
              <node package="{PACKAGE}" clickable="{'false' if selected == '首页' else 'true'}" enabled="true" focusable="true" selected="{'true' if selected == '首页' else 'false'}" bounds="[85,2759][412,2977]">
                <node package="{PACKAGE}" text="首页" clickable="false" focusable="false" selected="false" bounds="[206,2882][292,2946]" />
              </node>
              <node package="{PACKAGE}" clickable="{'false' if selected == '字体库' else 'true'}" enabled="true" focusable="true" selected="{'true' if selected == '字体库' else 'false'}" bounds="[406,2763][721,2973]">
                <node package="{PACKAGE}" text="字体库" clickable="false" focusable="false" selected="false" bounds="[501,2882][627,2943]" />
              </node>
              <node package="{PACKAGE}" clickable="true" enabled="true" focusable="true" selected="false" bounds="[721,2763][1036,2973]">
                <node package="{PACKAGE}" text="组合" clickable="false" bounds="[837,2882][921,2943]" />
              </node>
              <node package="{PACKAGE}" clickable="true" enabled="true" focusable="true" selected="false" bounds="[1036,2763][1349,2973]">
                <node package="{PACKAGE}" text="设置" clickable="false" bounds="[1151,2882][1235,2943]" />
              </node>
            </node>
          </node>
        </hierarchy>''')

    def test_uses_clickable_parent_and_bottom_tab_instead_of_home_card(self):
        target = tab_target(self.hierarchy(), "字体库", PACKAGE)
        self.assertEqual((563, 2868), center(target))
        self.assertEqual("true", target.get("clickable"))

    def test_recognizes_selected_compose_tab_without_clickable_flag(self):
        root = self.hierarchy()
        target = tab_target(root, "首页", PACKAGE)
        self.assertEqual((248, 2868), center(target))
        self.assertEqual("false", target.get("clickable"))
        self.assertTrue(page_ready(root, "首页", "当前字体", PACKAGE))

    def test_requires_selected_tab_and_actual_page_content(self):
        root = self.hierarchy("字体库")
        ET.SubElement(root[0], "node", {"package": PACKAGE, "text": "搜索你的字体"})
        self.assertTrue(page_ready(root, "字体库", "搜索你的字体", PACKAGE))
        self.assertFalse(page_ready(self.hierarchy(), "字体库", "当前字体", PACKAGE))
        self.assertFalse(page_ready(root, "字体库", "字体组合", PACKAGE))

    def test_does_not_fall_back_to_home_card_when_tab_group_is_incomplete(self):
        root = self.hierarchy()
        dock = root[0][-1]
        dock.remove(dock[-1])
        with self.assertRaisesRegex(ValueError, "not found"):
            tab_target(root, "字体库", PACKAGE)

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
