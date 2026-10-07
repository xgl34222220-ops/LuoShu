#!/usr/bin/env python3
"""Host tests for the screenshot harness; these do not claim emulator coverage."""

import unittest
import xml.etree.ElementTree as ET
import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from android_ui_smoke import (
    action_disabled, anchors_preserved, app_labels, center, choice_selected, content_anchors,
    crash_reason, label_target, orientation_matches, page_ready, tab_target,
    SmokeRun, instrumentation_results, library_state_preserved, assert_single_stage_startup,
    legacy_manual_colors_ready, legacy_monet_unavailable,
    app_window_bounds, logical_input_size, scroll_content, visible_scroll_anchors,
    scroll_progress, visible_action, visible_text, ScrollBudget,
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

    def scroll_hierarchy(self, offset=0, target=None, selected=True):
        root = ET.fromstring(f'''<hierarchy><node package="{PACKAGE}" bounds="[0,0][1080,1920]">
          <node package="{PACKAGE}" text="fixed header" bounds="[40,70][600,120]" />
          <node package="{PACKAGE}" scrollable="true" bounds="[0,140][1080,1794]">
            <node package="{PACKAGE}" text="anchor one" bounds="[40,{300 + offset}][700,{360 + offset}]" />
            <node package="{PACKAGE}" text="anchor two" bounds="[40,{800 + offset}][700,{860 + offset}]" />
            <node package="{PACKAGE}" scrollable="true" bounds="[40,500][1040,600]" />
          </node>
          <node package="com.android.systemui" text="system" bounds="[0,1794][1080,1920]" />
        </node></hierarchy>''')
        if target:
            ET.SubElement(root[0][1], "node", {"package": PACKAGE, "text": target,
                "bounds": "[40,1200][600,1320]", "clickable": "true", "enabled": "true",
                "selected": "true" if selected else "false"})
        return root

    def test_scroll_geometry_uses_logical_override_and_current_rotation_not_screenshot_size(self):
        root = self.scroll_hierarchy()
        wm = "Physical size: 1440x3120\nOverride size: 1080x1920\n"
        self.assertEqual((1080, 1920), logical_input_size(wm, app_window_bounds(root, PACKAGE)))
        self.assertEqual((1920, 1080), logical_input_size(wm, (0, 0, 1920, 1080)))
        with self.assertRaisesRegex(RuntimeError, "exceeds logical"):
            logical_input_size(wm, (0, 0, 1440, 3120))
        with self.assertRaisesRegex(RuntimeError, "Cannot verify"):
            logical_input_size("unknown screen size", (0, 0, 1080, 1920))

    def test_scroll_geometry_uses_actual_vertical_container_and_excludes_header_system_and_chips(self):
        root = self.scroll_hierarchy()
        node, rect = scroll_content(root, PACKAGE)
        self.assertIs(root[0][1], node)
        self.assertEqual((0, 140, 1080, 1794), rect)
        self.assertEqual({"anchor one": (370, 330), "anchor two": (370, 830)},
                         visible_scroll_anchors(root, PACKAGE))
        root[0][1].set("scrollable", "false")
        with self.assertRaisesRegex(RuntimeError, "vertical App"):
            scroll_content(root, PACKAGE)

    def test_visible_targets_reject_offscreen_and_disabled_semantics(self):
        root = self.scroll_hierarchy(target="收藏")
        self.assertIsNotNone(visible_action(root, "收藏", PACKAGE))
        self.assertTrue(visible_text(root, "收藏", PACKAGE))
        target = root[0][1][-1]
        target.set("bounds", "[40,20][600,80]")
        self.assertFalse(visible_text(root, "收藏", PACKAGE))
        with self.assertRaisesRegex(ValueError, "outside visible"):
            visible_action(root, "收藏", PACKAGE)
        target.set("bounds", "[40,120][600,200]")
        with self.assertRaisesRegex(ValueError, "outside visible"):
            visible_action(root, "收藏", PACKAGE)
        target.set("bounds", "[40,1200][600,1320]")
        target.set("enabled", "false")
        with self.assertRaisesRegex(ValueError, "Enabled action"):
            visible_action(root, "收藏", PACKAGE)

    def test_scroll_progress_uses_directional_visible_anchor_positions_not_node_counts(self):
        before = {"a": (40, 600), "b": (40, 1000)}
        stationary_extra_nodes = {**before, "new asynchronous status": (40, 1400)}
        self.assertFalse(scroll_progress(before, stationary_extra_nodes, "up"))
        self.assertFalse(scroll_progress(before, {"a": (40, 650), "b": (40, 1050)}, "up"))
        self.assertTrue(scroll_progress(before, {"a": (40, 550), "b": (40, 950)}, "up"))
        self.assertFalse(scroll_progress({}, {}, "up"))
        self.assertFalse(scroll_progress(before, {}, "up"))
        with self.assertRaises(ValueError):
            scroll_progress(before, before, "sideways")

    def test_legacy_decor_navigation_bar_cannot_count_as_scroll_content_or_action_visibility(self):
        root = self.scroll_hierarchy(target="收藏")
        root[0][1].set("bounds", "[0,63][1080,1920]")
        root[0][-1].set("package", PACKAGE)
        root[0][-1].set("resource-id", "android:id/navigationBarBackground")
        self.assertEqual((0, 63, 1080, 1794), scroll_content(root, PACKAGE)[1])
        root[0][1][-1].set("bounds", "[40,1820][600,1900]")
        with self.assertRaisesRegex(ValueError, "outside visible"):
            visible_action(root, "收藏", PACKAGE)

    def test_bounded_scroll_waits_for_measured_settled_progress_and_keeps_each_xml(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = SmokeRun(Path("app.apk"), Path(temporary), PACKAGE, None)
            initial = self.scroll_hierarchy()
            moved = self.scroll_hierarchy(offset=-100)
            reached = self.scroll_hierarchy(offset=-200, target="收藏")
            run.text = Mock(return_value="Physical size: 1440x3120\nOverride size: 1080x1920\n")
            run.adb = Mock()
            run.assert_running = Mock()
            run.hierarchy = Mock(side_effect=[initial, initial, moved, moved, reached])
            with patch("android_ui_smoke.time.sleep"):
                result = run.reach_content(lambda root: visible_action(root, "收藏", PACKAGE), "favorite row")
            self.assertIs(reached, result)
            self.assertEqual(2, run.adb.call_count)
            for call in run.adb.call_args_list:
                self.assertEqual(("shell", "input", "swipe"), call.args[:3])
                self.assertEqual("2000", call.args[-1])
                self.assertEqual("540", call.args[3])
                self.assertLess(int(call.args[4]), 1794)
                self.assertGreater(int(call.args[6]), 140)
            evidence = json.loads((Path(temporary) / "scroll-search-0001.json").read_text())
            self.assertTrue(evidence["passed"])
            self.assertEqual(5, len(evidence["samples"]))
            self.assertEqual([1080, 1920], evidence["samples"][0]["input_size"])
            self.assertTrue(all((Path(temporary) / sample["xml"]).is_file() for sample in evidence["samples"]))

    def test_bounded_scroll_stagnation_or_boundary_cannot_report_a_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = SmokeRun(Path("app.apk"), Path(temporary), PACKAGE, None)
            root = self.scroll_hierarchy()
            run.text = Mock(return_value="Physical size: 1080x1920\n")
            run.adb = Mock()
            run.assert_running = Mock()
            run.hierarchy = Mock(return_value=root)
            with patch("android_ui_smoke.time.sleep"), self.assertRaisesRegex(RuntimeError, "stalled or reached a boundary"):
                run.reach_content(lambda current: visible_text(current, "missing restoration help", PACKAGE), "help")
            self.assertEqual(1, run.adb.call_count)
            evidence = json.loads((Path(temporary) / "scroll-search-0001.json").read_text())
            self.assertFalse(evidence["passed"])
            self.assertEqual(9, len(evidence["samples"]))

    def test_bounded_scroll_gesture_and_total_time_exhaustion_cannot_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = SmokeRun(Path("app.apk"), Path(temporary), PACKAGE, None)
            run.text = Mock(return_value="Physical size: 1080x1920\n")
            run.adb = Mock()
            run.assert_running = Mock()
            run.hierarchy = Mock(return_value=self.scroll_hierarchy())
            with self.assertRaisesRegex(RuntimeError, "gesture budget exhausted"):
                run.reach_content(lambda current: False, "help", budget=ScrollBudget(max_gestures=0))
            budget = ScrollBudget()
            budget.deadline = 0
            with self.assertRaisesRegex(RuntimeError, "time budget exhausted"):
                run.reach_content(lambda current: True, "already visible but expired", budget=budget)
            run.adb.assert_not_called()

    def test_find_choice_never_turns_visible_unselected_filter_into_success(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = SmokeRun(Path("app.apk"), Path(temporary), PACKAGE, None)
            run.reach_content = Mock(return_value=self.scroll_hierarchy(target="收藏", selected=False))
            with self.assertRaisesRegex(RuntimeError, "no longer selected"):
                run.find_choice("收藏", direction="down")
            self.assertEqual("down", run.reach_content.call_args.kwargs["direction"])

    def test_bounded_scroll_preserves_app_anr_failure_even_when_target_is_visible(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = SmokeRun(Path("app.apk"), Path(temporary), PACKAGE, None)
            run.text = Mock(return_value="Physical size: 1080x1920\n")
            run.hierarchy = Mock(return_value=self.scroll_hierarchy(target="收藏"))
            run.assert_running = Mock(side_effect=RuntimeError("App ANR recorded by ActivityManager"))
            with self.assertRaisesRegex(RuntimeError, "App ANR"):
                run.reach_content(lambda root: visible_action(root, "收藏", PACKAGE), "favorite")
            self.assertFalse(json.loads((Path(temporary) / "scroll-search-0001.json").read_text())["passed"])

    def test_google_help_keeps_one_budget_real_export_entry_toggle_and_restoration_marker(self):
        from google_font_compat_smoke import CompatibilitySmokeRun
        with tempfile.TemporaryDirectory() as temporary:
            run = CompatibilitySmokeRun(Path("app.apk"), Path(temporary), PACKAGE, None)
            entry = self.scroll_hierarchy(target="Google 字体兼容")
            status = self.scroll_hierarchy()
            for label in ("当前状态", "恢复原设置", "重新检测"):
                ET.SubElement(status[0][1], "node", {"package": PACKAGE, "text": label,
                    "bounds": "[40,1100][600,1160]"})
            diagnostic = self.scroll_hierarchy(target="导出复发诊断")
            toggle = self.scroll_hierarchy(target="详细原理与影响范围")
            expanded = self.scroll_hierarchy(target="收起技术说明")
            help_root = self.scroll_hierarchy(target="停用或卸载洛书前，请先恢复原设置。")
            run.hierarchy = Mock(side_effect=[entry, status])
            run.assert_running = Mock()
            run.adb = Mock()
            run.capture = Mock()
            run.reach_content = Mock(side_effect=[diagnostic, toggle, help_root])
            run.wait_ui = Mock(return_value=expanded)
            with patch.object(SmokeRun, "run"):
                run.run()
            calls = run.reach_content.call_args_list
            self.assertEqual(3, len(calls))
            budget = calls[0].kwargs["budget"]
            self.assertTrue(all(call.kwargs["budget"] is budget for call in calls))
            self.assertEqual(8, budget.max_gestures)
            self.assertIsNotNone(calls[0].args[0](diagnostic))
            self.assertIsNotNone(calls[1].args[0](toggle))
            self.assertTrue(calls[2].args[0](help_root))
            self.assertFalse(calls[2].args[0](expanded))
            self.assertTrue(run.wait_ui.call_args.args[0](expanded))
            self.assertFalse(run.wait_ui.call_args.args[0](toggle))
            taps = [call for call in run.adb.call_args_list if call.args[:3] == ("shell", "input", "tap")]
            self.assertEqual(2, len(taps))  # Settings entry and real details toggle; export never tapped.
            self.assertIn(("google-font-diagnostic-entry", diagnostic), [call.args for call in run.capture.call_args_list])
            self.assertIn(("google-font-chinese-help", help_root), [call.args for call in run.capture.call_args_list])

    def test_reach_content_shared_budget_cannot_restart_gesture_allowance_for_later_help_stages(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = SmokeRun(Path("app.apk"), Path(temporary), PACKAGE, None)
            run.text = Mock(return_value="Physical size: 1080x1920\n")
            run.hierarchy = Mock(return_value=self.scroll_hierarchy())
            run.assert_running = Mock()
            run.adb = Mock()
            budget = ScrollBudget(max_gestures=1)
            budget.used = 1
            with self.assertRaisesRegex(RuntimeError, "gesture budget exhausted"):
                run.reach_content(lambda current: False, "later help stage", budget=budget)
            run.adb.assert_not_called()

    def test_orientation_uses_real_app_bounds(self):
        self.assertTrue(orientation_matches(self.hierarchy(), PACKAGE, landscape=False))
        self.assertFalse(orientation_matches(self.hierarchy(), PACKAGE, landscape=True))
        root = ET.fromstring(f'<hierarchy><node package="{PACKAGE}" bounds="[0,0][1920,1080]" /></hierarchy>')
        self.assertTrue(orientation_matches(root, PACKAGE, landscape=True))
        self.assertFalse(orientation_matches(root, "other.app", landscape=True))

    def saved_library(self, selected="字体库"):
        root = self.hierarchy(selected)
        ET.SubElement(root[0], "node", {"package": PACKAGE, "text": "筛选结果", "bounds": "[70,400][360,480]"})
        filter_node = ET.SubElement(root[0], "node", {"package": PACKAGE, "focusable": "true",
            "enabled": "true", "selected": "true", "bounds": "[215,26][367,129]"})
        ET.SubElement(filter_node, "node", {"package": PACKAGE, "text": "收藏", "bounds": "[257,89][325,97]"})
        return root

    def test_saved_library_can_preserve_state_while_search_is_offscreen(self):
        root = self.saved_library()
        before = content_anchors(root, PACKAGE)
        self.assertFalse(page_ready(root, "字体库", "搜索你的字体", PACKAGE))
        self.assertTrue(library_state_preserved(root, before, PACKAGE))
        # The original top-page assertion still requires its real search field.
        ET.SubElement(root[0], "node", {"package": PACKAGE, "text": "搜索你的字体", "bounds": "[70,200][1300,350]"})
        self.assertTrue(page_ready(root, "字体库", "搜索你的字体", PACKAGE))
        self.assertTrue(choice_selected(root, "收藏", PACKAGE))

    def test_saved_library_rejects_changed_tab_filter_marker_or_scroll(self):
        before = content_anchors(self.saved_library(), PACKAGE)
        self.assertFalse(library_state_preserved(self.saved_library("首页"), before, PACKAGE))
        root = self.saved_library()
        root[0][-1].set("selected", "false")
        self.assertFalse(library_state_preserved(root, before, PACKAGE))
        root = self.saved_library()
        root[0][-2].set("text", "另一个页面")
        self.assertFalse(library_state_preserved(root, before, PACKAGE))
        root = self.saved_library()
        root[0][-2].set("bounds", "[70,540][360,620]")
        self.assertFalse(library_state_preserved(root, before, PACKAGE))
        self.assertFalse(library_state_preserved(self.saved_library(), {}, PACKAGE))

    def legacy_palette(self):
        return ET.fromstring(f'''<hierarchy><node package="{PACKAGE}" bounds="[0,0][1080,1920]">
          <node package="{PACKAGE}" text="当前系统不支持壁纸取色，可直接选择主题色。" bounds="[40,400][1000,500]" />
          <node package="{PACKAGE}" text="曜紫" enabled="true" clickable="true" selected="false" bounds="[40,520][250,650]" />
          <node package="{PACKAGE}" text="青蓝" enabled="true" clickable="true" selected="true" bounds="[270,520][480,650]" />
          <node package="{PACKAGE}" text="需要 Android 12 或更高版本，当前可手动选色" bounds="[40,700][1000,750]" />
          <node package="{PACKAGE}" enabled="false" bounds="[40,760][1000,900]">
            <node package="{PACKAGE}" text="Monet 动态取色" enabled="true" bounds="[80,780][520,850]" />
          </node>
        </node></hierarchy>''')

    def test_legacy_colors_require_enabled_actions_and_no_wallpaper_claim(self):
        root = self.legacy_palette()
        self.assertTrue(legacy_manual_colors_ready(root, PACKAGE))
        root[0][1].set("enabled", "false")
        self.assertFalse(legacy_manual_colors_ready(root, PACKAGE))
        root = self.legacy_palette()
        ET.SubElement(root[0], "node", {"package": PACKAGE, "text": "已跟随壁纸取色；关闭动态取色后可选择主题色。"})
        self.assertFalse(legacy_manual_colors_ready(root, PACKAGE))

    def test_legacy_monet_requires_actual_disabled_semantics_and_version_notice(self):
        root = self.legacy_palette()
        self.assertTrue(legacy_monet_unavailable(root, PACKAGE))
        root[0][-1].set("enabled", "true")
        self.assertFalse(legacy_monet_unavailable(root, PACKAGE))
        root = self.legacy_palette()
        root[0][-2].set("text", "跟随系统壁纸强调色")
        self.assertFalse(legacy_monet_unavailable(root, PACKAGE))

    def test_optional_recording_failure_is_evidence_only_not_an_app_verdict(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = SmokeRun(Path("app.apk"), Path(temporary), PACKAGE, None)
            process = Mock(returncode=1)
            process.communicate.return_value = (b"", b"encoder not available")
            process.poll.return_value = 1
            run.finish_launch_recording(process)
            self.assertFalse(run.recordings[0]["available"])
            self.assertIn("encoder not available", run.recordings[0]["error"])
            self.assertEqual([], run.checks)

    def startup_log(self, events, pid="123"):
        return "\n".join(f"10-07 12:37:43.668 {pid} {pid} I LuoShuStartup: event={event} elapsedMs=12"
                         for event in events)

    def test_single_stage_startup_requires_current_pid_and_actual_content_evidence(self):
        events = ["first_decor_draw", "native_exit_received", "native_removed",
                  "content_draw_delivered", "launch_complete"]
        log = self.startup_log(events)
        self.assertEqual(events, assert_single_stage_startup(log, "123", 36))
        with self.assertRaisesRegex(RuntimeError, "missing startup evidence"):
            assert_single_stage_startup(log, "999", 36)
        with self.assertRaisesRegex(RuntimeError, "content_draw_delivered"):
            assert_single_stage_startup(self.startup_log(["first_decor_draw", "launch_complete"]), "123", 28)

    def test_startup_content_evidence_rejects_explicit_second_brand_but_needs_no_exit_callback(self):
        events = ["first_decor_draw", "content_draw_delivered", "launch_complete"]
        with self.assertRaisesRegex(RuntimeError, "second branded"):
            assert_single_stage_startup(self.startup_log(events + ["art_fade_start"]), "123", 36)
        # A platform-owned exit need not call App code. These events establish
        # content delivery only; every-frame checks reject actual re-covering.
        self.assertEqual(events, assert_single_stage_startup(self.startup_log(events), "123", 36))

    def test_single_stage_startup_legacy_and_late_native_callback_both_work(self):
        events = ["first_decor_draw", "content_draw_delivered", "launch_complete"]
        self.assertEqual(events, assert_single_stage_startup(self.startup_log(events), "123", 30))
        late = events + ["native_exit_received", "native_removed"]
        self.assertEqual(late, assert_single_stage_startup(self.startup_log(late), "123", 36))
        # Earlier-process art events cannot contaminate the current process's verdict.
        log = self.startup_log(["art_fade_start"], "999") + "\n" + self.startup_log(late)
        self.assertEqual(late, assert_single_stage_startup(log, "123", 36))

    def test_launch_recording_is_opt_in_without_replacing_the_real_launch_checks(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = SmokeRun(Path("app.apk"), Path(temporary), PACKAGE, None)
            root = self.hierarchy()
            run.launch_and_capture = Mock(return_value=root)
            run.adb = Mock(return_value=subprocess.CompletedProcess([], 0, b"baseline PNG", b""))
            run.begin_launch_recording = Mock(return_value=Mock())
            run.finish_launch_recording = Mock()
            self.assertIs(root, run.launch("cold-start"))
            run.begin_launch_recording.assert_not_called()
            run.launch_and_capture.assert_called_once_with("cold-start")
            run.record_launch = True
            self.assertIs(root, run.launch("cold-start"))
            run.begin_launch_recording.assert_called_once_with("cold-start")
            run.finish_launch_recording.assert_called_once_with(run.begin_launch_recording.return_value, "cold-start")
            run.begin_launch_recording.reset_mock()
            run.finish_launch_recording.reset_mock()
            self.assertIs(root, run.launch("repeat-cold-start"))
            run.begin_launch_recording.assert_called_once_with("repeat-cold-start")
            run.finish_launch_recording.assert_called_once_with(run.begin_launch_recording.return_value, "repeat-cold-start")

    def test_repeat_recording_has_distinct_file_and_waits_for_the_bounded_encoder(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = SmokeRun(Path("app.apk"), Path(temporary), PACKAGE, None)
            process = Mock(returncode=0)
            process.communicate.return_value = (b"", b"")
            def pull(*args, **kwargs):
                self.assertEqual(args[:2], ("pull", "/sdcard/luoshu-repeat-cold-start.mp4"))
                Path(args[2]).write_bytes(b"\x00\x00\x00\x18ftypmp42")
                return subprocess.CompletedProcess([], 0, b"", b"")
            run.adb = Mock(side_effect=pull)
            run.finish_launch_recording(process, "repeat-cold-start")
            process.communicate.assert_called_once_with(timeout=35)
            self.assertTrue(run.recordings[0]["available"])
            self.assertEqual(run.recordings[0]["file"], "repeat-cold-start.mp4")
            self.assertEqual(run.recordings[0]["time_limit_seconds"], 30)

    def test_visual_only_run_captures_both_themes_without_repeating_functional_suite(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = SmokeRun(Path("app.apk"), Path(temporary), PACKAGE, None,
                           record_launch=True, visual_launch_only=True)
            run.adb = Mock()
            run.text = Mock(return_value="36")
            run.launch = Mock()
            run.assert_running = Mock()
            run.verify_rapid_navigation = Mock(side_effect=AssertionError("Functional regression is a separate run"))
            run.run()
            self.assertEqual([call.args[0] for call in run.launch.call_args_list],
                             ["light-cold-start", "light-warm-start", "dark-cold-start", "dark-warm-start"])
            self.assertTrue(any(call.args == ("shell", "cmd", "uimode", "night", "yes")
                                for call in run.adb.call_args_list))
            run.verify_rapid_navigation.assert_not_called()
            run.assert_running.assert_called_once()

    def test_scroll_uses_live_content_and_override_dimensions(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = SmokeRun(Path("app.apk"), Path(temporary), PACKAGE, None)
            root = ET.fromstring(f'''<hierarchy><node package="{PACKAGE}" bounds="[0,0][1080,1920]">
              <node package="{PACKAGE}" scrollable="true" bounds="[0,63][1080,1700]">
                <node package="{PACKAGE}" text="管理字体库" bounds="[150,1300][400,1390]" />
              </node>
              <node package="{PACKAGE}" resource-id="android:id/navigationBarBackground" bounds="[0,1794][1080,1920]" />
            </node></hierarchy>''')
            run.text = Mock(return_value="Physical size: 1440x3120\nOverride size: 1080x1920\n")
            run.adb = Mock()
            run.scroll(root)
            run.adb.assert_called_once_with("shell", "input", "swipe", "540", "1307", "540", "472", "400")
            run.text = Mock(return_value="Physical size: 800x1280\n")
            with self.assertRaisesRegex(RuntimeError, "exceeds logical input"):
                run.scroll(root)

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

    def test_root_only_transient_snapshot_waits_for_real_content_without_a_gesture(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            run = SmokeRun(Path("app.apk"), output, PACKAGE, None, Path("snapshot.apk"))
            root_only = ET.fromstring(f'<hierarchy><node package="{PACKAGE}" '
                                     'class="android.widget.FrameLayout" bounds="[0,0][1080,1920]" /></hierarchy>')
            ready = self.scroll_hierarchy(target="收藏")
            run.hierarchy_once = Mock(side_effect=[root_only, ready])
            run.assert_running = Mock()
            run.adb = Mock()
            with patch("android_ui_smoke.time.sleep"):
                self.assertIs(ready, run.hierarchy())
            run.adb.assert_not_called()
            run.assert_running.assert_called_once()
            evidence = json.loads(next(output.glob("hierarchy-readiness-*.json")).read_text())
            self.assertEqual(1, len(evidence["rejected_snapshots"]))
            self.assertIsNotNone(visible_action(ready, "收藏", PACKAGE))

    def test_persistent_root_only_snapshot_is_bounded_and_cannot_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = SmokeRun(Path("app.apk"), Path(temporary), PACKAGE, None)
            root_only = ET.fromstring(f'<hierarchy><node package="{PACKAGE}" bounds="[0,0][1080,1920]" /></hierarchy>')
            run.hierarchy_once = Mock(return_value=root_only)
            run.assert_running = Mock()
            with patch("android_ui_smoke.time.monotonic", side_effect=[0, 1, 9, 9]), \
                    self.assertRaisesRegex(RuntimeError, "within 8s: window root only"):
                run.hierarchy()
            self.assertEqual(1, run.hierarchy_once.call_count)

    def test_root_only_readiness_wait_does_not_hide_an_app_anr(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = SmokeRun(Path("app.apk"), Path(temporary), PACKAGE, None)
            run.hierarchy_once = Mock(return_value=ET.fromstring('<hierarchy><node /></hierarchy>'))
            run.assert_running = Mock(side_effect=RuntimeError("App ANR recorded by ActivityManager"))
            with self.assertRaisesRegex(RuntimeError, "App ANR"):
                run.hierarchy()
            self.assertEqual(1, run.hierarchy_once.call_count)

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
