#!/usr/bin/env python3
"""Host tests for the screenshot harness; these do not claim emulator coverage."""

import unittest
import io
import xml.etree.ElementTree as ET
import json
import subprocess
import struct
import gzip
import os
import sys
import shutil
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
    focused_component, decode_raw_screencap, decompress_screencap_gzip, home_launcher_content, main,
)


PACKAGE = "io.github.xgl34222220.luoshu.debug"


class UiSmokeHarnessTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which("java"), "Java runtime is required for public snapshot cache compatibility checks")
    def test_java_snapshot_refresh_keeps_configuration_deadline_and_modern_clear_path(self):
        # Compile the production methods against only the public-interface test
        # doubles below. This tests host control flow, not Android window access.
        source = (Path(__file__).parent / "ui_snapshot/SnapshotInstrumentation.java").read_text()
        def production_method(marker):
            start = source.index(marker)
            opening = source.index("{", start)
            depth, end = 1, opening + 1
            while depth:
                depth += (source[end] == "{") - (source[end] == "}")
                end += 1
            return source[start:end]
        methods = production_method("private static JSONObject serviceInfoEvidence") + "\n" + production_method(
            "private static void refreshLegacyAccessibilityCache")
        start = source.index("if (Build.VERSION.SDK_INT >= 34)")
        branch = source[start:source.index("while (root == null", start)]
        harness = r'''
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.ArrayList;
public class SnapshotCacheCompatibilityTest {
  static class Build { static class VERSION { static int SDK_INT; } }
  static class SystemClock { static long now; static long uptimeMillis() { return now; } }
  static class Bundle extends LinkedHashMap<String, String> { void putString(String k, String v) { put(k, v); } }
  static class JSONObject extends LinkedHashMap<String, Object> {
    static final Object NULL = new Object();
    public JSONObject put(String k, Object v) { super.put(k, v); return this; }
  }
  static class JSONArray extends ArrayList<Object> { JSONArray put(Object v) { add(v); return this; } }
  static class AccessibilityServiceInfo {
    int flags=83, eventTypes=63, feedbackType=16, capabilities=1, interactive=7, noninteractive=11;
    long notificationTimeout=23;
    String[] packageNames={"owned.test", "second.test"};
    int getCapabilities() { return capabilities; }
    int getInteractiveUiTimeoutMillis() { if (Build.VERSION.SDK_INT<29) throw new AssertionError("API29 getter on legacy28"); return interactive; }
    int getNonInteractiveUiTimeoutMillis() { if (Build.VERSION.SDK_INT<29) throw new AssertionError("API29 getter on legacy28"); return noninteractive; }
    AccessibilityServiceInfo copy() {
      AccessibilityServiceInfo i=new AccessibilityServiceInfo();
      i.flags=flags; i.eventTypes=eventTypes; i.feedbackType=feedbackType; i.capabilities=capabilities;
      i.notificationTimeout=notificationTimeout; i.interactive=interactive; i.noninteractive=noninteractive;
      i.packageNames=packageNames==null?null:packageNames.clone(); return i;
    }
  }
  static class UiAutomation {
    AccessibilityServiceInfo original=new AccessibilityServiceInfo(), confirmed=original.copy();
    int reads, sets, clears, lateRead; boolean nativeClear=true, late, mutateInPlace;
    AccessibilityServiceInfo getServiceInfo() {
      reads++; SystemClock.now+=5; if(reads==lateRead)SystemClock.now=8100;
      return sets==0?original:confirmed;
    }
    void setServiceInfo(AccessibilityServiceInfo info) {
      if (info!=original) throw new AssertionError("Must resend the existing configuration object");
      sets++; SystemClock.now+=5;
      if (mutateInPlace) { original.flags++; confirmed=original; }
      if (late) SystemClock.now=8100;
    }
    boolean clearCache() { clears++; return nativeClear; }
  }
  static void require(boolean ok,String detail) { if (!ok) throw new AssertionError(detail); }
  static int cases;
  static void expectFailure(UiAutomation a,long deadline,String text) throws Exception {
    Bundle b=new Bundle();
    try { refresh(a,b,deadline); throw new AssertionError("Accepted invalid refresh: "+text); }
    catch (IllegalStateException e) { require(e.getMessage().contains(text),e.toString()); }
    require(!"true".equals(b.get("accessibility_service_info_unchanged")),"Failed refresh reported unchanged");
    cases++;
  }
  public static void main(String[] args) throws Exception {
    for (int sdk:new int[]{28,29,33}) {
      Build.VERSION.SDK_INT=sdk; SystemClock.now=0;
      UiAutomation a=new UiAutomation(); Bundle b=new Bundle(); refresh(a,b,8000);
      require(a.sets==1 && a.reads==2 && a.clears==0,"Legacy must use one public refresh/readback");
      require(a.original.flags==83 && a.original.eventTypes==63 && a.original.packageNames.length==2,"Scope changed");
      require("true".equals(b.get("accessibility_service_info_unchanged")),"Missing unchanged confirmation");
      require(b.get("accessibility_service_info_before").equals(b.get("accessibility_service_info_after")),"Configuration evidence differs");
      require("15".equals(b.get("accessibility_cache_refresh_ms")),"Refresh not measured inside deadline");
      cases++;
    }
    Build.VERSION.SDK_INT=28;
    SystemClock.now=0;UiAutomation unrestricted=new UiAutomation();Bundle unrestrictedResult=new Bundle();
    unrestricted.original.packageNames=null;unrestricted.confirmed.packageNames=null;
    refresh(unrestricted,unrestrictedResult,8000);
    require(unrestricted.original.packageNames==null && unrestricted.confirmed.packageNames==null,"Null package scope changed");
    require("true".equals(unrestrictedResult.get("accessibility_service_info_unchanged")),"Null scope not confirmed");cases++;
    for (int failure=0; failure<8; failure++) {
      SystemClock.now=0; UiAutomation a=new UiAutomation();
      switch(failure) {
        case 0:a.confirmed.flags++;break; case 1:a.confirmed.eventTypes++;break;
        case 2:a.confirmed.feedbackType++;break; case 3:a.confirmed.notificationTimeout++;break;
        case 4:a.confirmed.capabilities++;break; case 5:a.confirmed.packageNames=new String[]{"expanded.scope"};break;
        case 6:a.confirmed.packageNames=null;break; case 7:a.mutateInPlace=true;break;
      }
      expectFailure(a,8000,"configuration changed"); require(a.sets==1 && a.reads==2,"Unexpected reconnect or retry");
    }
    for(int failure=0;failure<2;failure++) {
      Build.VERSION.SDK_INT=33;SystemClock.now=0;UiAutomation a=new UiAutomation();
      if(failure==0)a.confirmed.interactive++;else a.confirmed.noninteractive++;
      expectFailure(a,8000,"configuration changed");
    }
    Build.VERSION.SDK_INT=28;SystemClock.now=0;UiAutomation missing=new UiAutomation();missing.original=null;
    expectFailure(missing,8000,"Cannot read");require(missing.sets==0,"Null configuration was submitted");
    SystemClock.now=0;UiAutomation unconfirmed=new UiAutomation();unconfirmed.confirmed=null;
    expectFailure(unconfirmed,8000,"Cannot confirm");require(unconfirmed.sets==1,"Unexpected retry");
    SystemClock.now=8000;UiAutomation expired=new UiAutomation();expectFailure(expired,8000,"deadline expired before cache");
    require(expired.reads==0 && expired.sets==0,"Work after deadline");
    SystemClock.now=0;UiAutomation initialReadLate=new UiAutomation();initialReadLate.lateRead=1;
    expectFailure(initialReadLate,8000,"deadline expired before public");
    require(initialReadLate.sets==0 && initialReadLate.reads==1,"Refresh continued after initial read exhausted deadline");
    SystemClock.now=0;UiAutomation late=new UiAutomation();late.late=true;
    expectFailure(late,8000,"deadline expired before service confirmation");
    require(late.reads==1 && late.sets==1,"Confirmation attempted after setter exhausted deadline");
    SystemClock.now=0;UiAutomation confirmationLate=new UiAutomation();confirmationLate.lateRead=2;
    expectFailure(confirmationLate,8000,"deadline expired during");
    for(int sdk:new int[]{34,36}) {
      Build.VERSION.SDK_INT=sdk;SystemClock.now=0;UiAutomation a=new UiAutomation();Bundle b=new Bundle();refresh(a,b,8000);
      require(a.clears==1 && a.sets==0 && a.reads==0,"Modern public clear path changed");
      require("true".equals(b.get("accessibility_cache_cleared")),"Missing native clear result");cases++;
      UiAutomation bad=new UiAutomation();bad.nativeClear=false;expectFailure(bad,8000,"Cannot clear");
    }
    System.out.println("Passed "+cases+" production Java compatibility cases");
  }
''' + methods + "\nstatic void refresh(UiAutomation automation, Bundle result, long deadline) throws Exception {\n" + branch + "\n}\n}\n"
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            file = directory / "SnapshotCacheCompatibilityTest.java"
            file.write_text(harness)
            java = shutil.which("java")
            compiled = subprocess.run([java, "--module", "jdk.compiler/com.sun.tools.javac.Main", "-d", str(directory), str(file)],
                                      capture_output=True, timeout=30)
            self.assertEqual(0, compiled.returncode, compiled.stderr.decode())
            exercised = subprocess.run([java, "-cp", str(directory), "SnapshotCacheCompatibilityTest"],
                                       capture_output=True, timeout=10)
            self.assertEqual(0, exercised.returncode, exercised.stderr.decode())
            self.assertIn("Passed 24 production Java compatibility cases", exercised.stdout.decode())

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

    def baseline_png(self, content=20, clock=0):
        from PIL import Image
        image = Image.new("RGB", (40, 80), (content, content, content))
        image.paste((clock, 0, 0), (0, 0, 40, 4))
        image.paste((0, clock, 0), (0, 76, 40, 80))
        output = io.BytesIO()
        image.save(output, format="PNG")
        return output.getvalue()

    def baseline_window(self, component="com.example.launcher/com.example.launcher.Home"):
        return (f"mCurrentFocus=Window{{abc u0 {component}}}\n"
                "InsetsSource id=1 type=statusBars frame=[0,0][40,4] visible=true\n"
                "InsetsSource id=2 type=navigationBars frame=[0,76][40,80] visible=true\n")

    def baseline_raw(self, content=20, clock=0):
        from PIL import Image
        with Image.open(io.BytesIO(self.baseline_png(content, clock))) as image:
            return struct.pack("<IIII", 40, 80, 1, 1) + image.convert("RGBA").tobytes()

    def baseline_hierarchy(self):
        return ET.fromstring('''<hierarchy><node package="com.example.launcher" bounds="[0,0][40,80]">
          <node package="com.example.launcher" resource-id="com.example.launcher:id/workspace" bounds="[0,4][40,76]">
            <node package="com.example.launcher" text="Maps" clickable="true" enabled="true" bounds="[3,40][12,55]" />
          </node></node></hierarchy>''')

    def prepare_baseline_reader(self, run):
        run.api_level = 36
        run.snapshot_apk = Path("reader.apk")
        run.snapshot_hierarchy = Mock(side_effect=lambda **kwargs: self.baseline_hierarchy())

    def baseline_batch(self, raw, window=None):
        window = self.baseline_window() if window is None else window
        return window.encode() + b"\x00LUOSHU_HOME_BASELINE_RAW_GZIP\x00" + gzip.compress(raw, compresslevel=1, mtime=0)

    def test_raw_screencap_preserves_every_rgb_pixel_and_uses_sdk_header(self):
        from PIL import Image
        rgb = bytes((3, 79, 251, 99, 0, 7, 211, 68, 145, 6, 234, 57))
        for sdk, header_bytes in ((25, 12), (26, 12), (27, 16), (28, 16), (36, 16)):
            for pixel_format in (1, 2, 3):
                with self.subTest(sdk=sdk, pixel_format=pixel_format):
                    pixels = rgb if pixel_format == 3 else b"".join(
                        rgb[index:index + 3] + bytes((255 if pixel_format == 1 else 0,))
                        for index in range(0, len(rgb), 3))
                    header = struct.pack("<III", 2, 2, pixel_format)
                    raw = header + (struct.pack("<I", 1) if header_bytes == 16 else b"") + pixels
                    image, metadata = decode_raw_screencap(raw, sdk)
                    self.assertEqual((2, 2), image.size)
                    self.assertEqual(rgb, image.tobytes())
                    encoded = io.BytesIO()
                    image.save(encoded, format="PNG", compress_level=1)
                    with Image.open(io.BytesIO(encoded.getvalue())) as png:
                        self.assertEqual((2, 2), png.size)
                        self.assertEqual(rgb, png.convert("RGB").tobytes())
                    self.assertEqual(header_bytes, metadata["header_bytes"])
                    self.assertEqual(1 if header_bytes == 16 else None, metadata["colorspace_id"])

    def test_raw_screencap_rejects_unknown_layout_gamut_alpha_and_exact_length_errors(self):
        valid = struct.pack("<IIII", 2, 1, 1, 1) + bytes((1, 2, 3, 255, 4, 5, 6, 255))
        malformed = [b"", valid[:15], valid[:-1], valid + b"x", valid[:12] + valid[16:],
                     struct.pack("<IIII", 0, 1, 1, 1),
                     struct.pack("<IIII", 2, 1, 4, 1) + b"\x00" * 4,
                     struct.pack("<IIII", 2, 1, 5, 1) + valid[16:],
                     struct.pack("<IIII", 2, 1, 1, 0) + valid[16:],
                     struct.pack("<IIII", 2, 1, 1, 2) + valid[16:],
                     valid[:-1] + b"\x7f", struct.pack(">IIII", 2, 1, 1, 1) + valid[16:]]
        for raw in malformed:
            with self.subTest(raw=raw), self.assertRaises(RuntimeError):
                decode_raw_screencap(raw, 36)
        with self.assertRaises(RuntimeError):
            decode_raw_screencap(valid, 25)
        for missing_sdk in (None, 0, True):
            with self.subTest(sdk=missing_sdk), self.assertRaises(RuntimeError):
                decode_raw_screencap(valid, missing_sdk)

    def test_launcher_readiness_rejects_root_logo_wrong_package_and_unusable_actions(self):
        home = "com.example.launcher/com.example.launcher.Home"
        self.assertTrue(home_launcher_content(self.baseline_hierarchy(), home))
        for failure in ("root", "logo", "wrong-package", "empty-container", "disabled", "not-clickable", "empty-label", "bad-bounds"):
            root = self.baseline_hierarchy()
            container, action = root[0][0], root[0][0][0]
            if failure == "root":
                root[0].remove(container)
            elif failure == "logo":
                container.set("resource-id", "com.example.launcher:id/splash_icon")
            elif failure == "wrong-package":
                action.set("package", PACKAGE)
            elif failure == "empty-container":
                container.remove(action)
            elif failure == "disabled":
                action.set("enabled", "false")
            elif failure == "not-clickable":
                action.set("clickable", "false")
            elif failure == "empty-label":
                action.set("text", "")
            elif failure == "bad-bounds":
                action.set("bounds", "[0,0][0,0]")
            with self.subTest(failure=failure):
                self.assertEqual([], home_launcher_content(root, home))

    def test_home_baseline_requires_stable_real_content_and_preserves_raw_final_png(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = SmokeRun(Path("app.apk"), Path(temporary), PACKAGE, None)
            self.prepare_baseline_reader(run)
            captures = [self.baseline_raw(10), self.baseline_raw(20),
                        self.baseline_raw(20, 1), self.baseline_raw(20, 2)]
            run.text = Mock(return_value="com.example.launcher/.Home\n")
            run.adb = Mock(side_effect=[subprocess.CompletedProcess([], 0, self.baseline_batch(png), b"") for png in captures])
            clock = [0.0]
            with patch("android_ui_smoke.time.monotonic", side_effect=lambda: clock[0]), \
                    patch("android_ui_smoke.time.sleep", side_effect=lambda duration: clock.__setitem__(0, clock[0] + duration)):
                baseline = run.wait_home_baseline("light-cold-start")
            from PIL import Image
            with Image.open(io.BytesIO(baseline)) as png:
                self.assertEqual((40, 80), png.size)
                self.assertEqual(decode_raw_screencap(captures[-1], 36)[0].tobytes(), png.convert("RGB").tobytes())
            self.assertEqual(baseline, (Path(temporary) / "light-cold-start-baseline-03.png").read_bytes())
            self.assertEqual(captures[-1], (Path(temporary) / "light-cold-start-baseline-03-screencap.raw").read_bytes())
            metadata = json.loads((Path(temporary) / "light-cold-start-baseline-readiness.json").read_text())
            self.assertEqual([1, 1, 2, 3], [sample["stable_captures"] for sample in metadata["samples"]])
            self.assertTrue(metadata["passed"])
            self.assertEqual([0, 4, 40, 76], metadata["samples"][-1]["content_bounds"])
            self.assertEqual("com.example.launcher/com.example.launcher.Home",
                             focused_component(self.baseline_window("com.example.launcher/.Home")))
            self.assertEqual(4, run.adb.call_count)
            for call, png in zip(run.adb.call_args_list, captures):
                self.assertEqual(("exec-out", "sh", "-c"), call.args[:3])
                self.assertIn("dumpsys window displays", call.args[3])
                self.assertTrue(call.args[3].endswith("screencap | gzip -1"))
                self.assertTrue(call.args[3].startswith("set -o pipefail || exit;"))
                self.assertNotIn("screencap -p", call.args[3])
                self.assertLessEqual(call.kwargs["timeout"], 10)
            self.assertEqual(4, run.snapshot_hierarchy.call_count)
            self.assertTrue(all(call.kwargs == {"deadline": 10} for call in run.snapshot_hierarchy.call_args_list))
            self.assertEqual(self.baseline_batch(captures[-1]),
                             (Path(temporary) / metadata["samples"][-1]["batch_raw"]).read_bytes())
            self.assertEqual(captures[-1], decompress_screencap_gzip(
                (Path(temporary) / metadata["samples"][-1]["screencap_gzip"]).read_bytes()))
            self.assertEqual(4, len({sample["hierarchy"] for sample in metadata["samples"]}))
            self.assertEqual("ui-automation-snapshot", run.hierarchy_backend)
            run.hierarchy_once()
            self.assertEqual(4, run.adb.call_count)  # No competing uiautomator connection.

    def test_visual_baseline_focus_or_motion_failure_never_starts_recording_and_keeps_deadline(self):
        for cause in ("wrong-focus", "moving-home", "launcher-splash"):
            with self.subTest(cause=cause), tempfile.TemporaryDirectory() as temporary:
                run = SmokeRun(Path("app.apk"), Path(temporary), PACKAGE, None,
                               record_launch=True, visual_launch_only=True)
                self.prepare_baseline_reader(run)
                if cause == "launcher-splash":
                    run.snapshot_hierarchy = Mock(return_value=ET.fromstring('<hierarchy><node package="com.example.launcher" bounds="[0,0][40,80]" /></hierarchy>'))
                home = self.baseline_window(f"{PACKAGE}/.MainActivity") if cause == "wrong-focus" else self.baseline_window()
                run.text = Mock(side_effect=lambda *args, **kwargs:
                                "com.example.launcher/.Home\n" if "resolve-activity" in args else home)
                captures = [self.baseline_raw(20), self.baseline_raw(30)]
                count = [0]
                def capture(*args, **kwargs):
                    png = captures[count[0] % 2] if cause == "moving-home" else captures[0]
                    count[0] += 1
                    return subprocess.CompletedProcess([], 0, self.baseline_batch(png, home), b"")
                run.adb = Mock(side_effect=capture)
                run.begin_launch_recording = Mock()
                run.launch_and_capture = Mock()
                clock = [0.0]
                with patch("android_ui_smoke.time.monotonic", side_effect=lambda: clock[0]), \
                        patch("android_ui_smoke.time.sleep", side_effect=lambda duration: clock.__setitem__(0, clock[0] + duration)), \
                        self.assertRaisesRegex(RuntimeError, "within 10s"):
                    run.launch("light-cold-start")
                run.begin_launch_recording.assert_not_called()
                run.launch_and_capture.assert_not_called()
                metadata = json.loads((Path(temporary) / "light-cold-start-baseline-readiness.json").read_text())
                self.assertFalse(metadata["passed"])
                self.assertEqual(10, metadata["elapsed_seconds"])
                self.assertTrue(metadata["samples"])
                self.assertTrue((Path(temporary) / metadata["samples"][-1]["window"]).is_file())
                self.assertTrue((Path(temporary) / metadata["samples"][-1]["screenshot"]).is_file())

    def test_warm_visual_launch_requires_one_existing_process_before_recording(self):
        for missing_or_ambiguous in ("", "123 456", "not-a-pid"):
            with self.subTest(pidof=missing_or_ambiguous), tempfile.TemporaryDirectory() as temporary:
                run = SmokeRun(Path("app.apk"), Path(temporary), PACKAGE, None,
                               record_launch=True, visual_launch_only=True)
                run.adb = Mock()
                run.text = Mock(side_effect=["36", missing_or_ambiguous, missing_or_ambiguous])
                run.launch = Mock()
                run.assert_running = Mock()
                with patch("android_ui_smoke.time.sleep"), \
                        self.assertRaisesRegex(RuntimeError, "warm launch requires one existing App PID"):
                    run.run()
                self.assertEqual(["light-cold-start", "dark-cold-start"], [call.args[0] for call in run.launch.call_args_list])
                self.assertFalse(any(check["check"].endswith("same-process") for check in run.checks))

    def test_baseline_combines_each_real_window_and_png_within_original_budget(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = SmokeRun(Path("app.apk"), Path(temporary), PACKAGE, None)
            self.prepare_baseline_reader(run)
            clock = [0.0]
            run.text = Mock(return_value="com.example.launcher/.Home\n")
            raw = self.baseline_raw()
            def capture(*args, **kwargs):
                clock[0] += 2.5
                return subprocess.CompletedProcess([], 0, self.baseline_batch(raw), b"")
            run.adb = Mock(side_effect=capture)
            with patch("android_ui_smoke.time.monotonic", side_effect=lambda: clock[0]), \
                    patch("android_ui_smoke.time.sleep", side_effect=lambda duration: clock.__setitem__(0, clock[0] + duration)):
                png = run.wait_home_baseline("light-cold-start")
                self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertEqual(3, run.adb.call_count)
            self.assertLess(clock[0], 10)
            metadata = json.loads((Path(temporary) / "light-cold-start-baseline-readiness.json").read_text())
            self.assertEqual(10, metadata["timeout_seconds"])
            self.assertEqual([1, 2, 3], [sample["stable_captures"] for sample in metadata["samples"]])
            self.assertEqual([2.5, 2.5, 2.5], [sample["capture_seconds"] for sample in metadata["samples"]])
            self.assertTrue(all(sample["launcher_content"] for sample in metadata["samples"]))

    def test_missing_or_corrupt_batch_png_fails_before_recording_and_keeps_raw(self):
        valid = self.baseline_raw()
        corrupted = bytearray(valid)
        corrupted[8] ^= 64
        malformed = (b"missing separator", self.baseline_batch(b"not PNG"),
                     self.baseline_batch(bytes(corrupted)), self.baseline_batch(valid[:-20]),
                     self.baseline_batch(valid) + b"\x00LUOSHU_HOME_BASELINE_RAW_GZIP\x00")
        for raw in malformed:
            with self.subTest(raw_length=len(raw)), tempfile.TemporaryDirectory() as temporary:
                run = SmokeRun(Path("app.apk"), Path(temporary), PACKAGE, None,
                               record_launch=True, visual_launch_only=True)
                self.prepare_baseline_reader(run)
                run.text = Mock(return_value="com.example.launcher/.Home\n")
                run.adb = Mock(return_value=subprocess.CompletedProcess([], 0, raw, b""))
                run.begin_launch_recording = Mock()
                run.launch_and_capture = Mock()
                with self.assertRaisesRegex(RuntimeError, "HOME baseline failed"):
                    run.launch("light-cold-start")
                run.begin_launch_recording.assert_not_called()
                run.launch_and_capture.assert_not_called()
                self.assertEqual(raw, (Path(temporary) / "light-cold-start-baseline-00-batch.bin").read_bytes())
                metadata = json.loads((Path(temporary) / "light-cold-start-baseline-readiness.json").read_text())
                self.assertFalse(metadata["passed"])
                self.assertEqual([], metadata["samples"])

    def test_baseline_batch_timeout_keeps_partial_raw_and_never_records(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = SmokeRun(Path("app.apk"), Path(temporary), PACKAGE, None,
                           record_launch=True, visual_launch_only=True)
            self.prepare_baseline_reader(run)
            run.text = Mock(return_value="com.example.launcher/.Home\n")
            partial = self.baseline_batch(b"partial PNG")
            def timeout(*args, **kwargs):
                cause = subprocess.TimeoutExpired("adb", kwargs["timeout"], output=partial, stderr=b"partial stderr")
                raise RuntimeError("adb timed out during baseline batch") from cause
            run.adb = Mock(side_effect=timeout)
            run.begin_launch_recording = Mock()
            run.launch_and_capture = Mock()
            with self.assertRaisesRegex(RuntimeError, "adb timed out during baseline batch"):
                run.launch("light-cold-start")
            run.begin_launch_recording.assert_not_called()
            run.launch_and_capture.assert_not_called()
            self.assertEqual(partial, (Path(temporary) / "light-cold-start-baseline-00-batch.bin").read_bytes())
            self.assertEqual(b"partial stderr", (Path(temporary) / "light-cold-start-baseline-00-stderr.txt").read_bytes())
            self.assertEqual(gzip.compress(b"partial PNG", compresslevel=1, mtime=0),
                             (Path(temporary) / "light-cold-start-baseline-00-screencap.raw.gz").read_bytes())
            self.assertFalse((Path(temporary) / "light-cold-start-baseline-00-screencap.raw").exists())

    def test_baseline_hierarchy_timeout_cannot_overwrite_the_raw_capture_or_record(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = SmokeRun(Path("app.apk"), Path(temporary), PACKAGE, None,
                           record_launch=True, visual_launch_only=True)
            self.prepare_baseline_reader(run)
            run.text = Mock(return_value="com.example.launcher/.Home\n")
            batch = self.baseline_batch(self.baseline_raw())
            run.adb = Mock(return_value=subprocess.CompletedProcess([], 0, batch, b"capture stderr"))
            def timeout(**kwargs):
                cause = subprocess.TimeoutExpired("adb", 1, output=b"hierarchy response", stderr=b"hierarchy stderr")
                raise RuntimeError("hierarchy deadline expired") from cause
            calls = [0]
            def second_hierarchy(**kwargs):
                calls[0] += 1
                return self.baseline_hierarchy() if calls[0] == 1 else timeout(**kwargs)
            run.snapshot_hierarchy = Mock(side_effect=second_hierarchy)
            run.begin_launch_recording = Mock()
            run.launch_and_capture = Mock()
            with self.assertRaisesRegex(RuntimeError, "hierarchy deadline expired"):
                run.launch("light-cold-start")
            run.begin_launch_recording.assert_not_called()
            run.launch_and_capture.assert_not_called()
            self.assertEqual(batch, (Path(temporary) / "light-cold-start-baseline-00-batch.bin").read_bytes())
            self.assertEqual(b"capture stderr", (Path(temporary) / "light-cold-start-baseline-00-stderr.txt").read_bytes())
            metadata = json.loads((Path(temporary) / "light-cold-start-baseline-readiness.json").read_text())
            self.assertFalse(metadata["passed"])
            self.assertIn("capture_seconds", metadata["samples"][0])
            self.assertIn("hierarchy", metadata["failed_sample"])
            self.assertFalse((Path(temporary) / "light-cold-start-baseline-01-batch.bin").exists())
            self.assertEqual("hierarchy", metadata["failed_sample"]["stage"])

    def test_baseline_shared_deadline_includes_every_live_hierarchy_read(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = SmokeRun(Path("app.apk"), Path(temporary), PACKAGE, None,
                           record_launch=True, visual_launch_only=True)
            self.prepare_baseline_reader(run)
            run.text = Mock(return_value="com.example.launcher/.Home\n")
            clock = [0.0]
            def capture(*args, **kwargs):
                clock[0] += 2.5
                return subprocess.CompletedProcess([], 0, self.baseline_batch(self.baseline_raw()), b"")
            def hierarchy(**kwargs):
                self.assertEqual(10, kwargs["deadline"])
                clock[0] += .7
                return self.baseline_hierarchy()
            run.adb = Mock(side_effect=capture)
            run.snapshot_hierarchy = Mock(side_effect=hierarchy)
            run.begin_launch_recording = Mock()
            run.launch_and_capture = Mock()
            with patch("android_ui_smoke.time.monotonic", side_effect=lambda: clock[0]), \
                    patch("android_ui_smoke.time.sleep", side_effect=lambda duration: clock.__setitem__(0, clock[0] + duration)), \
                    self.assertRaisesRegex(RuntimeError, "within 10s"):
                run.launch("light-cold-start")
            run.begin_launch_recording.assert_not_called()
            run.launch_and_capture.assert_not_called()
            metadata = json.loads((Path(temporary) / "light-cold-start-baseline-readiness.json").read_text())
            self.assertFalse(metadata["passed"])
            self.assertEqual(10, metadata["timeout_seconds"])
            self.assertEqual(3, metadata["required_stable_captures"])
            self.assertEqual([.7, .7], [sample["hierarchy_seconds"] for sample in metadata["samples"]])
            self.assertEqual(.7, metadata["failed_sample"]["hierarchy_seconds"])

    def test_screencap_gzip_is_lossless_and_rejects_crc_size_truncation_and_extra_members(self):
        raw = self.baseline_raw()
        compressed = gzip.compress(raw, compresslevel=1, mtime=0)
        self.assertEqual(raw, decompress_screencap_gzip(compressed))
        crc = bytearray(compressed)
        crc[-8] ^= 1
        size = bytearray(compressed)
        size[-4] ^= 1
        malformed = (b"", compressed[:9], compressed[:-1], compressed[:-8],
                     bytes(crc), bytes(size), compressed + b"\x00",
                     compressed + compressed, raw)
        for frame in malformed:
            with self.subTest(frame_length=len(frame)), self.assertRaises(RuntimeError):
                decompress_screencap_gzip(frame)

    def test_baseline_unpresented_system_bars_fail_and_keep_exact_full_png_and_raw(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as temporary:
            run = SmokeRun(Path("app.apk"), Path(temporary), PACKAGE, None,
                           record_launch=True, visual_launch_only=True)
            self.prepare_baseline_reader(run)
            run.text = Mock(return_value="com.example.launcher/.Home\n")
            # The ee7de2bb light sample's actual failure: an explicit zero-sized,
            # invisible navigation source must not become a guessed crop.
            window = self.baseline_window().replace(
                "type=navigationBars frame=[0,76][40,80] visible=true",
                "type=navigationBars frame=[0,0][0,0] visible=false")
            raw = self.baseline_raw()
            batch = self.baseline_batch(raw, window)
            run.adb = Mock(return_value=subprocess.CompletedProcess([], 0, batch, b""))
            run.begin_launch_recording = Mock()
            run.launch_and_capture = Mock()
            with self.assertRaisesRegex(RuntimeError, "Cannot identify real HOME system bars"):
                run.launch("light-cold-start")
            run.begin_launch_recording.assert_not_called()
            run.launch_and_capture.assert_not_called()
            self.assertEqual(batch, (Path(temporary) / "light-cold-start-baseline-00-batch.bin").read_bytes())
            self.assertEqual(raw, (Path(temporary) / "light-cold-start-baseline-00-screencap.raw").read_bytes())
            with Image.open(Path(temporary) / "light-cold-start-baseline-00.png") as png:
                self.assertEqual((40, 80), png.size)
                self.assertEqual(decode_raw_screencap(raw, 36)[0].tobytes(), png.convert("RGB").tobytes())
            metadata = json.loads((Path(temporary) / "light-cold-start-baseline-readiness.json").read_text())
            self.assertFalse(metadata["passed"])
            self.assertEqual([], metadata["samples"])
            self.assertEqual("content-bounds", metadata["failed_sample"]["stage"])
            self.assertIn("png_encode_seconds", metadata["failed_sample"])

    def test_baseline_capture_pipeline_failure_or_corrupt_gzip_never_records_and_keeps_bytes(self):
        raw = self.baseline_raw()
        valid_batch = self.baseline_batch(raw)
        for cause in ("capture-failed", "bad-gzip"):
            with self.subTest(cause=cause), tempfile.TemporaryDirectory() as temporary:
                run = SmokeRun(Path("app.apk"), Path(temporary), PACKAGE, None,
                               record_launch=True, visual_launch_only=True)
                self.prepare_baseline_reader(run)
                run.text = Mock(return_value="com.example.launcher/.Home\n")
                batch = valid_batch if cause == "capture-failed" else valid_batch[:-1]
                run.adb = Mock(return_value=subprocess.CompletedProcess(
                    [], 1 if cause == "capture-failed" else 0, batch, b"real capture stderr"))
                run.begin_launch_recording = Mock()
                run.launch_and_capture = Mock()
                with self.assertRaisesRegex(RuntimeError, "HOME baseline failed"):
                    run.launch("light-cold-start")
                run.begin_launch_recording.assert_not_called()
                run.launch_and_capture.assert_not_called()
                self.assertEqual(batch, (Path(temporary) / "light-cold-start-baseline-00-batch.bin").read_bytes())
                self.assertEqual(b"real capture stderr", (Path(temporary) / "light-cold-start-baseline-00-stderr.txt").read_bytes())
                compressed = batch.split(b"\x00LUOSHU_HOME_BASELINE_RAW_GZIP\x00")[1]
                self.assertEqual(compressed, (Path(temporary) / "light-cold-start-baseline-00-screencap.raw.gz").read_bytes())
                self.assertFalse((Path(temporary) / "light-cold-start-baseline-00-screencap.raw").exists())

    def test_capture_shell_frames_only_screencap_bytes_and_preserves_pipeline_failure(self):
        # Exercise the generated shell pipeline on the host. AOSP tag evidence
        # establishes Android mksh/gzip availability; this is not a device run.
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            run = SmokeRun(Path("app.apk"), directory, PACKAGE, None)
            self.prepare_baseline_reader(run)
            run.text = Mock(return_value="com.example.launcher/.Home\n")
            raw = self.baseline_raw()
            run.adb = Mock(return_value=subprocess.CompletedProcess([], 0, self.baseline_batch(raw), b""))
            with patch("android_ui_smoke.time.sleep"):
                run.wait_home_baseline("light-cold-start")
            command = run.adb.call_args.args[3]
            binaries = directory / "bin"
            binaries.mkdir()
            dumpsys = binaries / "dumpsys"
            dumpsys.write_text(f"#!{sys.executable}\nimport sys\nsys.stdout.buffer.write({self.baseline_window().encode()!r})\n")
            dumpsys.chmod(0o755)
            screencap = binaries / "screencap"
            for exit_code in (0, 7):
                screencap.write_text(f"#!{sys.executable}\nimport sys\nsys.stdout.buffer.write({raw!r})\nsys.exit({exit_code})\n")
                screencap.chmod(0o755)
                environment = {**os.environ, "PATH": str(binaries) + os.pathsep + os.environ["PATH"]}
                result = subprocess.run(["bash", "-c", command], env=environment, capture_output=True, timeout=5)
                self.assertEqual(exit_code, result.returncode)
                window, compressed = result.stdout.split(b"\x00LUOSHU_HOME_BASELINE_RAW_GZIP\x00")
                self.assertEqual(self.baseline_window().encode(), window)
                self.assertEqual(raw, decompress_screencap_gzip(compressed))

    def test_launch_stage_host_timings_do_not_treat_am_total_time_as_current_elapsed(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = SmokeRun(Path("app.apk"), Path(temporary), PACKAGE, None)
            clock = [0.0]
            def text(*args, **kwargs):
                if "start" in args:
                    clock[0] += 2
                    return "Status: ok\nTotalTime: 173202\nWaitTime: 2729\n"
                clock[0] += 1 if "pidof" in args else 2
                return "9449" if "pidof" in args else "real window transcript"
            def page(*args):
                clock[0] += 3
                return self.hierarchy()
            def capture(*args):
                clock[0] += 4
            def logcat(*args):
                clock[0] += 2
                return f"Displayed {PACKAGE}/.MainActivity: +2s202ms"
            run.text = Mock(side_effect=text)
            run.wait_page = Mock(side_effect=page)
            run.capture = Mock(side_effect=capture)
            run.logcat = Mock(side_effect=logcat)
            run.record = Mock()
            with patch("android_ui_smoke.time.monotonic", side_effect=lambda: clock[0]):
                run.launch_and_capture("warm-start")
            timing = run.record.call_args.kwargs
            self.assertEqual(14, timing["ui_ready_seconds"])
            self.assertEqual(2, timing["am_command_seconds"])
            self.assertEqual(3, timing["page_wait_seconds"])
            self.assertEqual(4, timing["home_capture_seconds"])
            self.assertEqual(5, timing["startup_evidence_seconds"])
            self.assertEqual("173202", timing["am_total_time_ms"])
            self.assertIn("startup evidence collection", timing["ui_ready_seconds_scope"])

    def test_cold_baseline_error_is_not_masked_by_missing_or_failed_warm_pid(self):
        for pid_result in ("", RuntimeError("pidof connection timed out")):
            with self.subTest(pid_result=str(pid_result)), tempfile.TemporaryDirectory() as temporary:
                run = SmokeRun(Path("app.apk"), Path(temporary), PACKAGE, None,
                               record_launch=True, visual_launch_only=True)
                run.adb = Mock()
                run.text = Mock(side_effect=["36", pid_result, ""])
                run.launch = Mock(side_effect=RuntimeError("HOME baseline did not become focused and stable within 10s"))
                run.assert_running = Mock(side_effect=RuntimeError("later pidof must not mask earlier error"))
                with self.assertRaises(RuntimeError) as failure:
                    run.run()
                self.assertIn("light-cold-start: HOME baseline", str(failure.exception))
                self.assertIn("warm recording skipped", str(failure.exception))
                self.assertEqual(["light-cold-start", "dark-cold-start"], [call.args[0] for call in run.launch.call_args_list])
                run.assert_running.assert_not_called()
                self.assertEqual([], run.recordings)
                self.assertFalse(any(check.get("passed") for check in run.checks))

    def test_warm_visual_launch_rejects_a_restarted_process(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = SmokeRun(Path("app.apk"), Path(temporary), PACKAGE, None,
                           record_launch=True, visual_launch_only=True)
            run.adb = Mock()
            run.text = Mock(side_effect=["36", "123", "456", "789", "789"])
            run.launch = Mock()
            run.assert_running = Mock()
            with patch("android_ui_smoke.time.sleep"), \
                    self.assertRaisesRegex(RuntimeError, "warm resume changed App PID 123 to 456"):
                run.run()
            self.assertEqual(4, run.launch.call_count)
            self.assertEqual(["dark-warm-start-same-process"], [check["check"] for check in run.checks])

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
            run.snapshot_session = Mock(nonce="test-session",
                capture=Mock(return_value=(instrumentation_results(transcript), ET.tostring(self.hierarchy()).decode())))
            root = run.snapshot_hierarchy()
            self.assertTrue(page_ready(root, "首页", "当前字体", PACKAGE))
            metadata = json.loads((output / "hierarchy-snapshot-0002.json").read_text())
            self.assertEqual("13", metadata["attempts"])
            self.assertEqual("1200", metadata["wait_ms"])
            self.assertEqual("focused-window:7", metadata["root_source"])
            run.snapshot_session.capture.assert_called_once_with("hierarchy-0002.xml")
            # A true system tree is still necessary; delayed success never skips
            # the selected-tab and actual-content checks used by the real run.
            self.assertFalse(page_ready(root, "字体库", "当前字体", PACKAGE))

    def test_exhausted_snapshot_wait_preserves_diagnostics_and_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            run = SmokeRun(Path("app.apk"), output, PACKAGE, None, Path("snapshot.apk"))
            transcript = ("INSTRUMENTATION_RESULT: wait_ms=8001\nINSTRUMENTATION_RESULT: attempts=79\n"
                          "INSTRUMENTATION_RESULT: root_source=unavailable\n"
                          f"INSTRUMENTATION_RESULT: last_root_package={PACKAGE}\n"
                          "INSTRUMENTATION_RESULT: last_root_window_id=7\n"
                          "INSTRUMENTATION_RESULT: last_root_child_count=0\n"
                          "INSTRUMENTATION_RESULT: last_root_visible_child_count=0\n"
                          "INSTRUMENTATION_RESULT: root_refresh_attempts=3\n"
                          "INSTRUMENTATION_RESULT: root_refresh_successes=2\n"
                          "INSTRUMENTATION_RESULT: root_refresh_failures=1\n"
                          'INSTRUMENTATION_RESULT: window_counts=[{"windows":0,"active":0,"focused":0}]\n'
                          "INSTRUMENTATION_RESULT: error=IllegalStateException: No active accessibility window\n"
                          "INSTRUMENTATION_RESULT: snapshot=failed\nINSTRUMENTATION_CODE: 0\n")
            run.snapshot_session = Mock(nonce="test-session",
                capture=Mock(return_value=(instrumentation_results(transcript), None)))
            with self.assertRaisesRegex(RuntimeError, "No active accessibility window"):
                run.snapshot_hierarchy()
            run.snapshot_session.capture.assert_called_once_with("hierarchy-0000.xml")
            metadata = json.loads((output / "hierarchy-snapshot-0000.json").read_text())
            self.assertEqual("8001", metadata["wait_ms"])
            self.assertEqual("79", metadata["attempts"])
            self.assertEqual("failed", metadata["snapshot"])
            self.assertEqual("7", metadata["last_root_window_id"])
            self.assertEqual("3", metadata["root_refresh_attempts"])
            self.assertEqual(0, json.loads(metadata["window_counts"])[0]["windows"])
            self.assertEqual("failed", instrumentation_results(transcript)["snapshot"])


class SnapshotCleanupHarnessTest(unittest.TestCase):
    def test_main_always_closes_session_and_preserves_primary_failure_and_anr(self):
        for diagnostic_failure in (False, True):
            with self.subTest(diagnostic_failure=diagnostic_failure), tempfile.TemporaryDirectory() as temporary:
                output = Path(temporary)
                apk = output / "app.apk"
                apk.write_bytes(b"APK path fixture")
                run = SmokeRun(apk, output, PACKAGE, None)
                run.run = Mock(side_effect=RuntimeError("real snapshot wait exhausted"))
                run.adb = Mock(return_value=subprocess.CompletedProcess([], 0, b"", b""))
                def diagnostics():
                    (output / "logcat.txt").write_text(f"ActivityManager: ANR in {PACKAGE}\n")
                    if diagnostic_failure:
                        raise OSError("diagnostic file error")
                run.diagnostics = Mock(side_effect=diagnostics)
                run.close_snapshot_session = Mock(side_effect=RuntimeError("owned helper cleanup failed"))
                arguments = ["android_ui_smoke.py", "--apk", str(apk), "--output", str(output)]
                with patch("android_ui_smoke.sys.argv", arguments), patch("android_ui_smoke.SmokeRun", return_value=run):
                    self.assertEqual(1, main())
                run.close_snapshot_session.assert_called_once()
                summary = json.loads((output / "summary.json").read_text())
                self.assertFalse(summary["passed"])
                self.assertIn("real snapshot wait exhausted", summary["error"])
                self.assertIn("owned helper cleanup failed", summary["error"])
                self.assertIn("App ANR", summary["error"])
                if diagnostic_failure:
                    self.assertIn("diagnostic file error", summary["error"])

    def test_cleanup_failure_alone_cannot_make_a_run_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            apk = output / "app.apk"
            apk.write_bytes(b"APK path fixture")
            run = SmokeRun(apk, output, PACKAGE, None)
            run.run = Mock()
            run.diagnostics = Mock()
            run.close_snapshot_session = Mock(side_effect=RuntimeError("owned helper cleanup failed"))
            arguments = ["android_ui_smoke.py", "--apk", str(apk), "--output", str(output)]
            with patch("android_ui_smoke.sys.argv", arguments), patch("android_ui_smoke.SmokeRun", return_value=run):
                self.assertEqual(1, main())
            self.assertFalse(json.loads((output / "summary.json").read_text())["passed"])


class QuickReturnHarnessTest(unittest.TestCase):
    def hierarchy(self, *, dock: bool, offset: int = 0):
        root = ET.fromstring(f'''<hierarchy><node package="{PACKAGE}" bounds="[0,0][1080,1920]">
          <node package="{PACKAGE}" scrollable="true" bounds="[0,89][1080,1920]">
            <node package="{PACKAGE}" text="管理字体库" bounds="[155,{389 + offset}][295,{450 + offset}]" />
            <node package="{PACKAGE}" text="系统默认" bounds="[242,{848 + offset}][398,{909 + offset}]" />
          </node>
        </node></hierarchy>''')
        if dock:
            navigation = ET.SubElement(root[0], "node", {"package": PACKAGE, "bounds": "[60,1680][1020,1850]"})
            for index, label in enumerate(("首页", "字体库", "组合", "设置")):
                left = 60 + index * 240
                item = ET.SubElement(navigation, "node", {"package": PACKAGE, "enabled": "true",
                    "focusable": "true", "selected": "true" if label == "字体库" else "false",
                    "clickable": "false" if label == "字体库" else "true",
                    "bounds": f"[{left},1680][{left + 240},1850]"})
                ET.SubElement(item, "node", {"package": PACKAGE, "text": label,
                    "bounds": f"[{left + 60},1770][{left + 180},1830]"})
        return root

    def test_visible_navigation_needs_no_gesture(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = SmokeRun(Path("app.apk"), Path(temporary), PACKAGE, None)
            ready = self.hierarchy(dock=True)
            run.hierarchy = Mock(return_value=ready)
            run.adb = Mock()
            run.wait_ui = Mock()
            self.assertIs(ready, run.ensure_dock())
            run.adb.assert_not_called()
            run.wait_ui.assert_not_called()

    def test_slow_reverse_gesture_preserves_geometry_and_real_navigation_proof(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            run = SmokeRun(Path("app.apk"), output, PACKAGE, None)
            before, ready = self.hierarchy(dock=False), self.hierarchy(dock=True, offset=60)
            run.hierarchy = Mock(return_value=before)
            clock = [0.0]
            run.adb = Mock(side_effect=lambda *args, **kwargs: clock.__setitem__(0, 2.5))

            def wait(predicate, description, timeout):
                self.assertEqual("Quick Return navigation", description)
                self.assertEqual(27.5, timeout)
                clock[0] = 3.0
                self.assertTrue(predicate(ready))
                return ready

            run.wait_ui = Mock(side_effect=wait)
            with patch("android_ui_smoke.time.monotonic", side_effect=lambda: clock[0]):
                self.assertIs(ready, run.ensure_dock())
            run.adb.assert_called_once_with("shell", "input", "swipe", "540", "768", "540", "883", "2000")
            evidence = json.loads((output / "quick-return-0001.json").read_text())
            self.assertTrue(evidence["passed"])
            self.assertEqual(2000, evidence["gesture"]["duration_ms"])
            self.assertEqual(2.5, evidence["gesture_elapsed_seconds"])
            self.assertEqual(3.0, evidence["elapsed_seconds"])
            self.assertEqual({"首页", "字体库", "组合", "设置"}, set(evidence["navigation"]))
            self.assertEqual("true", evidence["navigation"]["字体库"]["selected"])
            self.assertEqual(ET.tostring(before), ET.tostring(ET.parse(output / evidence["before_xml"]).getroot()))
            self.assertEqual(ET.tostring(ready), ET.tostring(ET.parse(output / evidence["after_xml"]).getroot()))

    def test_failed_reveal_keeps_before_after_and_does_not_report_a_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            run = SmokeRun(Path("app.apk"), output, PACKAGE, None)
            hidden = self.hierarchy(dock=False)
            run.hierarchy = Mock(return_value=hidden)
            run.adb = Mock()

            def wait(predicate, description, timeout):
                with self.assertRaises(ValueError):
                    predicate(hidden)
                raise RuntimeError("Quick Return navigation did not become ready")

            run.wait_ui = Mock(side_effect=wait)
            with self.assertRaisesRegex(RuntimeError, "Quick Return navigation did not become ready"):
                run.ensure_dock()
            evidence = json.loads((output / "quick-return-0001.json").read_text())
            self.assertFalse(evidence["passed"])
            self.assertTrue(evidence["after_snapshot_received"])
            self.assertEqual(evidence["before_anchors"], evidence["after_anchors"])
            self.assertIn("did not become ready", evidence["error"])
            self.assertTrue((output / evidence["before_xml"]).is_file())
            self.assertTrue((output / evidence["after_xml"]).is_file())

    def test_gesture_time_counts_toward_the_existing_thirty_second_budget(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            run = SmokeRun(Path("app.apk"), output, PACKAGE, None)
            run.hierarchy = Mock(return_value=self.hierarchy(dock=False))
            clock = [0.0]
            run.adb = Mock(side_effect=lambda *args, **kwargs: clock.__setitem__(0, 31.0))
            run.wait_ui = Mock()
            with patch("android_ui_smoke.time.monotonic", side_effect=lambda: clock[0]), \
                    self.assertRaisesRegex(RuntimeError, "exhausted its 30s budget"):
                run.ensure_dock()
            run.wait_ui.assert_not_called()
            evidence = json.loads((output / "quick-return-0001.json").read_text())
            self.assertFalse(evidence["passed"])
            self.assertFalse(evidence["after_snapshot_received"])
            self.assertEqual(30, evidence["timeout_seconds"])

    def test_incomplete_navigation_returned_by_a_wait_cannot_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            run = SmokeRun(Path("app.apk"), output, PACKAGE, None)
            run.hierarchy = Mock(return_value=self.hierarchy(dock=False))
            run.adb = Mock()
            incomplete = self.hierarchy(dock=True)
            incomplete[0][-1].remove(incomplete[0][-1][-1])
            run.wait_ui = Mock(return_value=incomplete)
            with self.assertRaisesRegex(ValueError, "not found"):
                run.ensure_dock()
            evidence = json.loads((output / "quick-return-0001.json").read_text())
            self.assertFalse(evidence["passed"])
            self.assertTrue(evidence["after_snapshot_received"])


if __name__ == "__main__":
    unittest.main()
