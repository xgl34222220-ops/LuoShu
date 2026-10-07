#!/usr/bin/env python3
"""Host tests for the screenshot harness; these do not claim emulator coverage."""

import unittest
import xml.etree.ElementTree as ET
import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import Mock

from android_ui_smoke import (
    action_disabled, anchors_preserved, app_labels, center, choice_selected, content_anchors,
    crash_reason, label_target, orientation_matches, page_ready, tab_target,
    SmokeRun, instrumentation_results,
)


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

    def test_choice_uses_actual_enabled_selected_semantics(self):
        root = ET.fromstring(f'''<hierarchy><node package="{PACKAGE}" bounds="[0,0][1080,1920]">
          <node package="{PACKAGE}" text="浅色" enabled="true" clickable="true" selected="true" bounds="[40,400][300,540]" />
          <node package="{PACKAGE}" text="深色" enabled="true" clickable="true" selected="false" bounds="[320,400][580,540]" />
          <node package="other.app" text="跟随系统" enabled="true" clickable="true" selected="true" bounds="[620,400][900,540]" />
        </node></hierarchy>''')
        self.assertTrue(choice_selected(root, "浅色", PACKAGE))
        self.assertFalse(choice_selected(root, "深色", PACKAGE))
        self.assertFalse(choice_selected(root, "跟随系统", PACKAGE))
        self.assertNotIn("跟随系统", app_labels(root, PACKAGE))

    def test_action_resolves_semantic_parent_and_rejects_disabled_ancestor(self):
        root = ET.fromstring(f'''<hierarchy><node package="{PACKAGE}" bounds="[0,0][1080,1920]">
          <node package="{PACKAGE}" enabled="true" clickable="true" bounds="[40,400][1000,620]">
            <node package="{PACKAGE}" text="外观与主题" clickable="false" bounds="[120,420][520,500]" />
          </node>
        </node></hierarchy>''')
        self.assertEqual((520, 510), center(label_target(root, "外观与主题", PACKAGE)))
        root[0][0].set("enabled", "false")
        with self.assertRaisesRegex(ValueError, "Enabled action"):
            label_target(root, "外观与主题", PACKAGE)

    def test_does_not_guess_an_action_from_visible_noninteractive_text(self):
        root = ET.fromstring(f'''<hierarchy><node package="{PACKAGE}" bounds="[0,0][1080,1920]">
          <node package="{PACKAGE}" text="收藏" clickable="false" bounds="[40,400][300,540]" />
        </node></hierarchy>''')
        self.assertFalse(choice_selected(root, "收藏", PACKAGE))
        with self.assertRaisesRegex(ValueError, "Enabled action"):
            label_target(root, "收藏", PACKAGE)

    def test_disabled_action_reads_ancestor_semantics_without_tapping(self):
        root = ET.fromstring(f'''<hierarchy><node package="{PACKAGE}" bounds="[0,0][1080,1920]">
          <node package="{PACKAGE}" enabled="false" clickable="false" bounds="[40,400][300,540]">
            <node package="{PACKAGE}" text="刷新字体库" enabled="true" bounds="[80,440][260,500]" />
          </node>
        </node></hierarchy>''')
        self.assertTrue(action_disabled(root, "刷新字体库", PACKAGE))
        root[0][0].set("enabled", "true")
        self.assertFalse(action_disabled(root, "刷新字体库", PACKAGE))
        self.assertFalse(action_disabled(root, "missing", PACKAGE))

    def test_scroll_anchors_exclude_dock_duplicates_and_foreign_package(self):
        root = self.hierarchy()
        ET.SubElement(root[0], "node", {"package": PACKAGE, "text": "系统默认字体", "bounds": "[200,1400][700,1500]"})
        ET.SubElement(root[0], "node", {"package": "other.app", "text": "foreign", "bounds": "[200,1400][700,1500]"})
        positions = content_anchors(root, PACKAGE)
        self.assertEqual((450, 1450), positions["系统默认字体"])
        self.assertNotIn("字体库", positions)
        self.assertNotIn("foreign", positions)
        ET.SubElement(root[0], "node", {"package": PACKAGE, "text": "系统默认字体", "bounds": "[200,1600][700,1700]"})
        self.assertNotIn("系统默认字体", content_anchors(root, PACKAGE))

    def test_scroll_preservation_rejects_missing_moved_or_empty_anchors(self):
        before = {"系统默认字体": (200, 700), "清除筛选": (400, 1100)}
        self.assertTrue(anchors_preserved(before, {"系统默认字体": (200, 705), "清除筛选": (400, 1100)}))
        self.assertFalse(anchors_preserved(before, {"系统默认字体": (200, 700)}))
        self.assertFalse(anchors_preserved(before, {"系统默认字体": (200, 830), "清除筛选": (400, 1100)}))
        self.assertFalse(anchors_preserved({}, {}))

    def test_orientation_uses_real_app_bounds(self):
        self.assertTrue(orientation_matches(self.hierarchy(), PACKAGE, landscape=False))
        self.assertFalse(orientation_matches(self.hierarchy(), PACKAGE, landscape=True))
        root = ET.fromstring(f'<hierarchy><node package="{PACKAGE}" bounds="[0,0][1920,1080]" /></hierarchy>')
        self.assertTrue(orientation_matches(root, PACKAGE, landscape=True))
        self.assertFalse(orientation_matches(root, "other.app", landscape=True))

    def test_successful_platform_dump_stays_on_normal_backend_and_keeps_cli_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            run = SmokeRun(Path("app.apk"), output, PACKAGE, None, Path("snapshot.apk"))
            xml = ET.tostring(self.hierarchy(), encoding="utf-8")
            responses = [subprocess.CompletedProcess([], 0, b"", b""),
                         subprocess.CompletedProcess([], 0, b"UI hierchary dumped to: /sdcard/luoshu-ui-smoke.xml", b""),
                         subprocess.CompletedProcess([], 0, xml, b"")]
            run.adb = Mock(side_effect=responses)
            run.snapshot_hierarchy = Mock(side_effect=AssertionError("Normal reader must stay in use"))
            root = run.hierarchy()
            self.assertTrue(page_ready(root, "首页", "当前字体", PACKAGE))
            self.assertEqual("uiautomator-cli", run.hierarchy_backend)
            evidence = json.loads((output / "hierarchy-dump-0001.json").read_text())
            self.assertEqual(0, evidence["returncode"])
            self.assertIn("dumped to", evidence["stdout"])

    def test_exit_zero_idle_failure_is_preserved_and_real_reader_is_cached(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            run = SmokeRun(Path("app.apk"), output, PACKAGE, None, Path("snapshot.apk"))
            empty = subprocess.CompletedProcess([], 0, b"", b"")
            run.adb = Mock(side_effect=[empty,
                subprocess.CompletedProcess([], 0, b"", b"ERROR: could not get idle state.\n"),
                subprocess.CompletedProcess([], 1, b"", b"cat: No such file or directory\n"),
                empty, subprocess.CompletedProcess([], 0, b"probe is writable", b""), empty])
            run.snapshot_hierarchy = Mock(return_value=self.hierarchy())
            self.assertTrue(page_ready(run.hierarchy(), "首页", "当前字体", PACKAGE))
            self.assertEqual("ui-automation-snapshot", run.hierarchy_backend)
            self.assertIn("could not get idle state", run.checks[0]["reason"])
            evidence = json.loads((output / "hierarchy-dump-0001.json").read_text())
            self.assertEqual(0, evidence["returncode"])
            self.assertIn("could not get idle state", evidence["stderr"])
            self.assertEqual(0, json.loads((output / "hierarchy-storage-probe-0001.json").read_text())["touch_returncode"])
            previous_commands = run.adb.call_count
            run.hierarchy()
            self.assertEqual(previous_commands, run.adb.call_count)
            self.assertEqual(2, run.snapshot_hierarchy.call_count)

    def test_dump_failure_without_real_reader_remains_a_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            run = SmokeRun(Path("app.apk"), output, PACKAGE, None)
            empty = subprocess.CompletedProcess([], 0, b"", b"")
            run.adb = Mock(side_effect=[empty,
                subprocess.CompletedProcess([], 0, b"ERROR: null root node returned by UiTestAutomationBridge.", b""),
                subprocess.CompletedProcess([], 1, b"", b"missing"), empty, empty, empty])
            with self.assertRaisesRegex(RuntimeError, "null root"):
                run.hierarchy()
            self.assertEqual("uiautomator-cli", run.hierarchy_backend)

    def test_failed_snapshot_is_not_reported_as_a_successful_fallback(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = SmokeRun(Path("app.apk"), Path(temporary), PACKAGE, None, Path("snapshot.apk"))
            empty = subprocess.CompletedProcess([], 0, b"", b"")
            run.adb = Mock(side_effect=[empty,
                subprocess.CompletedProcess([], 0, b"ERROR: could not get idle state.", b""),
                subprocess.CompletedProcess([], 1, b"", b"missing"), empty, empty, empty])
            run.snapshot_hierarchy = Mock(side_effect=RuntimeError("No real active window"))
            with self.assertRaisesRegex(RuntimeError, "No real active window"):
                run.hierarchy()
            self.assertEqual([], run.checks)

    def test_snapshot_wait_diagnostics_preserve_a_delayed_real_window_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            run = SmokeRun(Path("app.apk"), output, PACKAGE, None, Path("snapshot.apk"))
            run.hierarchy_attempts = 2
            transcript = ("INSTRUMENTATION_RESULT: wait_ms=1200\n"
                          "INSTRUMENTATION_RESULT: attempts=13\n"
                          "INSTRUMENTATION_RESULT: root_source=focused-window:7\n"
                          f"INSTRUMENTATION_RESULT: root_package={PACKAGE}\n"
                          "INSTRUMENTATION_RESULT: snapshot=ok\nINSTRUMENTATION_CODE: -1\n")
            run.adb = Mock(side_effect=[subprocess.CompletedProcess([], 0, transcript.encode(), b""),
                                       subprocess.CompletedProcess([], 0, ET.tostring(self.hierarchy()), b"")])
            root = run.snapshot_hierarchy()
            self.assertTrue(page_ready(root, "首页", "当前字体", PACKAGE))
            metadata = json.loads((output / "hierarchy-snapshot-0002.json").read_text())
            self.assertEqual("13", metadata["attempts"])
            self.assertEqual("1200", metadata["wait_ms"])
            self.assertEqual("focused-window:7", metadata["root_source"])
            self.assertEqual(20, run.adb.call_args_list[0].kwargs["timeout"])
            # A true system tree is still necessary; delayed success never skips
            # the selected-tab and actual-content checks used by the real run.
            self.assertFalse(page_ready(root, "字体库", "当前字体", PACKAGE))

    def test_exhausted_snapshot_wait_preserves_diagnostics_and_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            run = SmokeRun(Path("app.apk"), output, PACKAGE, None, Path("snapshot.apk"))
            transcript = ("INSTRUMENTATION_RESULT: wait_ms=8001\nINSTRUMENTATION_RESULT: attempts=79\n"
                          "INSTRUMENTATION_RESULT: root_source=unavailable\n"
                          "INSTRUMENTATION_RESULT: error=IllegalStateException: No active accessibility window\n"
                          "INSTRUMENTATION_RESULT: snapshot=failed\nINSTRUMENTATION_CODE: 0\n")
            run.adb = Mock(return_value=subprocess.CompletedProcess([], 0, transcript.encode(), b""))
            with self.assertRaisesRegex(RuntimeError, "No active accessibility window"):
                run.snapshot_hierarchy()
            self.assertEqual(1, run.adb.call_count)
            metadata = json.loads((output / "hierarchy-snapshot-0000.json").read_text())
            self.assertEqual("8001", metadata["wait_ms"])
            self.assertEqual("79", metadata["attempts"])
            self.assertEqual("failed", metadata["snapshot"])
            self.assertEqual("failed", instrumentation_results(transcript)["snapshot"])


if __name__ == "__main__":
    unittest.main()
