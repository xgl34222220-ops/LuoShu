#!/usr/bin/env python3
"""Host tests for the screenshot harness; these do not claim emulator coverage."""

import unittest
import io
import xml.etree.ElementTree as ET
import json
import subprocess
import struct
import gzip
import hashlib
import os
import sys
import shutil
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
from ui_snapshot_session import HELPER, UiSnapshotSession

from android_ui_smoke import (
    action_disabled, anchors_preserved, app_labels, bounds, center, choice_selected, content_anchors,
    crash_reason, label_target, orientation_matches, page_ready, tab_target,
    SmokeRun, instrumentation_results, library_state_preserved, assert_single_stage_startup,
    legacy_manual_colors_ready, legacy_monet_unavailable,
    app_window_bounds, logical_input_size, scroll_content, visible_scroll_anchors,
    scroll_progress, visible_action, visible_control, visible_text, ScrollBudget,
    focused_component, home_window_state, decode_raw_screencap, decompress_screencap_gzip, home_launcher_content, main,
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
        return ET.fromstring(f'''<hierarchy rotation="0">
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
        root = ET.fromstring(f'''<hierarchy rotation="0"><node package="{PACKAGE}" bounds="[0,0][1080,1920]">
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
        self.assertEqual((1080, 1920), logical_input_size(wm, app_window_bounds(root, PACKAGE), root))
        landscape = ET.fromstring('<hierarchy rotation="1" />')
        self.assertEqual((1920, 1080), logical_input_size(wm, (0, 0, 1920, 1080), landscape))
        with self.assertRaisesRegex(RuntimeError, "exceeds logical"):
            logical_input_size(wm, (0, 0, 1440, 3120), root)
        with self.assertRaisesRegex(RuntimeError, "Cannot verify"):
            logical_input_size("unknown screen size", (0, 0, 1080, 1920), root)

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

    def baseline_window(self, component="com.example.launcher/com.example.launcher.Home", showing=False):
        return (f"mCurrentFocus=Window{{abc u0 {component}}}\n"
                f"isKeyguardShowing={str(showing).lower()}\n"
                "InsetsSource id=1 type=statusBars frame=[0,0][40,4] visible=true\n"
                "InsetsSource id=2 type=navigationBars frame=[0,76][40,80] visible=true\n")

    def baseline_policy(self, showing=False, current_user=0, occluded=False):
        return ("WINDOW MANAGER POLICY STATE (dumpsys window policy)\n"
                "    KeyguardServiceDelegate\n"
                f"      showing={str(showing).lower()}\n"
                f"      occluded={str(occluded).lower()}\n"
                f"      currentUser={current_user}\n"
                "    Looper state:\n      currentUser=-10000\n")

    def baseline_adb(self, *, side_effect=None, return_value=None):
        capture = Mock(side_effect=side_effect, return_value=return_value)
        def command(*args, **kwargs):
            if args == ("exec-out", "sh", "-c", "dumpsys window policy && dumpsys window displays"):
                return subprocess.CompletedProcess([], 0,
                    (self.baseline_policy() + self.baseline_window()).encode(), b"probe stderr")
            return capture(*args, **kwargs)
        return Mock(side_effect=command)

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
        run.snapshot_session = Mock(spec=UiSnapshotSession)
        run.snapshot_hierarchy = Mock(side_effect=lambda **kwargs: self.baseline_hierarchy())

    def baseline_batch(self, raw, window=None, policy=None):
        window = self.baseline_window() if window is None else window
        policy = self.baseline_policy() if policy is None else policy
        return (policy + window).encode() + b"\x00LUOSHU_HOME_BASELINE_RAW_GZIP\x00" + gzip.compress(raw, compresslevel=1, mtime=0)

    def home_connection_fixture(self, directory, *, deferred=False, failed_policy=False):
        # Fixed host scheduling costs/private-file bytes, not Android latency.
        # Only the early begin call is deferred in the serial comparison.
        from ui_snapshot_session_test import Clock, PrivateProtocol
        clock = Clock()
        events = []
        policy_finished = [False]
        self.enterContext(patch('android_ui_smoke.time.monotonic', side_effect=clock.monotonic))
        self.enterContext(patch('android_ui_smoke.time.sleep', side_effect=clock.sleep))
        run = SmokeRun(Path('app.apk'), directory, PACKAGE, None, snapshot_apk=Path('reader.apk'))
        run.api_level = 36
        session = UiSnapshotSession(run.adb_command, directory)
        run.snapshot_session = session
        protocol = PrivateProtocol(session, clock)
        protocol.xml = ET.tostring(self.baseline_hierarchy())
        process = Mock(pid=12345, returncode=0)
        process.poll.return_value = None
        process.wait.return_value = 0

        def launch(command, **kwargs):
            events.append(('popen', clock.now))
            protocol.ready_delay = clock.now - 100 + 6
            return process
        popen = self.enterContext(patch('ui_snapshot_session.subprocess.Popen', side_effect=launch))
        self.enterContext(patch.object(session, '_start_readers'))
        def publication(basename, deadline):
            if basename == 'ready.json':
                clock.now = max(clock.now, min(100 + protocol.ready_delay, deadline))
            return protocol.wait_publication(basename, deadline)
        self.enterContext(patch.object(session, '_wait_publication', side_effect=publication))
        self.enterContext(patch.object(session, '_finish_readers', return_value=(b'INSTRUMENTATION_CODE: -1\n', b'')))

        def transport(command, **kwargs):
            args = command[len(session.adb_command):]
            if args[:2] == ['shell', '-T'] and 'request-' in args[-1]:
                self.assertTrue(policy_finished[0])
                events.append(('root-request', clock.now))
            if command[-1].endswith('/ready.json'):
                self.assertTrue(policy_finished[0])
                events.append(('ready-cat', clock.now))
            return protocol.run(command, **kwargs)
        self.enterContext(patch('ui_snapshot_session.subprocess.run', side_effect=transport))

        def resolve(*args, **kwargs):
            self.assertIn('resolve-activity', args)
            events.append(('resolve', clock.now))
            clock.sleep(.5)
            return 'com.example.launcher/.Home\n'
        run.text = Mock(side_effect=resolve)
        raw = self.baseline_raw()
        def command(*args, **kwargs):
            self.assertAlmostEqual(110 - clock.now, kwargs['timeout'])
            if args == ('exec-out', 'sh', '-c', 'dumpsys window policy && dumpsys window displays'):
                events.append(('policy', clock.now))
                clock.sleep(.6)
                policy_finished[0] = True
                if failed_policy:
                    # A valid ready notice may be queued by the owned reader
                    # before this failed probe; cleanup must retain that FAIL.
                    notice = json.dumps({'protocol': 1, 'nonce': session.nonce, 'basename': 'ready.json'}).encode()
                    session._publication_frame([(b'luoshu_snapshot_published', notice)], b'1')
                return subprocess.CompletedProcess([], 7 if failed_policy else 0,
                    (self.baseline_policy() + self.baseline_window()).encode(), b'initial probe bytes')
            self.assertTrue(policy_finished[0])
            self.assertEqual(len(protocol.requests), len(protocol.xml_reads))
            events.append(('frame', clock.now))
            if kwargs['timeout'] < .5:
                clock.sleep(kwargs['timeout'])
                cause = subprocess.TimeoutExpired('adb', kwargs['timeout'], output=b'partial frame', stderr=b'frame timeout')
                raise RuntimeError('fixed frame cost exceeded original HOME deadline') from cause
            clock.sleep(.5)
            return subprocess.CompletedProcess([], 0, self.baseline_batch(raw), b'frame bytes')
        run.adb = Mock(side_effect=command)
        if deferred:
            begin = session.begin
            def defer_until_policy(deadline):
                if not policy_finished[0]:
                    events.append(('deferred-begin', clock.now))
                    return
                return begin(deadline)
            session.begin = defer_until_policy
        return run, session, protocol, clock, events, popen

    def test_home_begin_overlaps_fixed_prefix_cost_and_keeps_three_fresh_captures(self):
        results = {}
        for deferred in (False, True):
            with self.subTest(deferred=deferred), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                run, session, protocol, clock, events, popen = self.home_connection_fixture(directory, deferred=deferred)
                if deferred:
                    with self.assertRaisesRegex(RuntimeError, 'original HOME deadline'):
                        run.wait_home_baseline('light-cold-start')
                else:
                    self.assertTrue(run.wait_home_baseline('light-cold-start').startswith(b'\x89PNG'))
                metadata = json.loads((directory / 'light-cold-start-baseline-readiness.json').read_text())
                self.assertEqual(100, metadata['started_monotonic_seconds'])
                self.assertEqual(110, metadata['deadline_monotonic_seconds'])
                self.assertEqual(110, metadata['session_begin']['deadline_monotonic_seconds'])
                self.assertEqual(110, session._first_capture_deadline)
                self.assertEqual(110, session._ready_json_timing['deadline_monotonic_seconds'])
                self.assertEqual(3, len(protocol.requests))
                self.assertEqual(3, len(protocol.xml_reads))
                self.assertEqual(3, len({value['request_id'] for value in protocol.requests}))
                self.assertEqual(['hierarchy-0001.xml', 'hierarchy-0002.xml', 'hierarchy-0003.xml'],
                                 [value['filename'] for value in protocol.requests])
                self.assertTrue(all(value['root_wait_ms'] == 8000 for value in protocol.requests))
                self.assertEqual([1, 2] if deferred else [1, 2, 3],
                                 [sample['stable_captures'] for sample in metadata['samples']])
                self.assertEqual(not deferred, metadata['passed'])
                self.assertEqual(.5, metadata['home_resolve_seconds'])
                self.assertEqual(.6, metadata['initial_window_state']['command_seconds'])
                self.assertEqual(3, sum(event == 'frame' for event, _ in events))
                self.assertEqual(1, sum(event == 'ready-cat' for event, _ in events))
                popen.assert_called_once()
                session.close()
                results['serial' if deferred else 'overlap'] = {'home': metadata, 'events': events,
                    'first_root_request_elapsed_seconds': next(at - 100 for event, at in events if event == 'root-request')}
        self.assertAlmostEqual(9.3, results['overlap']['home']['elapsed_seconds'])
        self.assertAlmostEqual(10, results['serial']['home']['elapsed_seconds'])
        self.assertAlmostEqual(1.1, results['serial']['first_root_request_elapsed_seconds'] -
                               results['overlap']['first_root_request_elapsed_seconds'])
        self.assertEqual('popen', results['overlap']['events'][0][0])
        self.assertEqual('resolve', results['overlap']['events'][1][0])
        evidence_directory = os.environ.get('LUOSHU_HOME_SCHEDULING_EVIDENCE_DIR')
        if evidence_directory:
            target = Path(evidence_directory)
            target.mkdir(parents=True, exist_ok=True)
            (target / 'fixed-host-cost-overlap-comparison.json').write_text(json.dumps(
                {'scope': 'synthetic host scheduling fixture; no Android performance result',
                 'fixed_cost_seconds': {'connection_ready': 6, 'resolve': .5, 'initial_policy': .6,
                    'private_command': .1, 'frame': .5, 'between_frames': .4}, 'results': results}, indent=2) + '\n')

    def test_home_initial_policy_failure_after_begin_keeps_no_root_and_failed_cleanup(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            run, session, protocol, clock, events, popen = self.home_connection_fixture(directory, failed_policy=True)
            with self.assertRaisesRegex(RuntimeError, 'initial window state probe failed') as primary:
                run.wait_home_baseline('light-cold-start')
            self.assertEqual(['popen', 'resolve', 'policy'], [event for event, _ in events])
            self.assertEqual([], protocol.requests)
            self.assertEqual([], protocol.xml_reads)
            self.assertFalse(session.ready)
            self.assertIsNone(session._ready_json_timing)
            with self.assertRaisesRegex(RuntimeError, 'unconsumed publication notice at close'):
                run.close_snapshot_session()
            self.assertIn('initial window state probe failed', str(primary.exception))
            self.assertNotIn('consumed_monotonic_seconds', session._ready_notice_timing)
            self.assertIn(['shell', 'am', 'force-stop', HELPER],
                          [command[len(run.adb_command):] for command, _ in protocol.calls])
            self.assertTrue(all(HELPER in ' '.join(command) for command, _ in protocol.calls))
            metadata = json.loads((directory / 'light-cold-start-baseline-readiness.json').read_text())
            self.assertFalse(metadata['passed'])
            self.assertEqual([], metadata['samples'])
            popen.assert_called_once()

    def test_home_begin_failure_never_probes_or_retries_or_publishes_a_root_request(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            run, session, protocol, clock, events, popen = self.home_connection_fixture(directory)
            popen.side_effect = OSError('connection begin failed')
            with self.assertRaisesRegex(RuntimeError, 'connection begin failed'):
                run.wait_home_baseline('light-cold-start')
            run.text.assert_not_called()
            run.adb.assert_not_called()
            self.assertEqual([], protocol.requests)
            self.assertEqual(set(), session.filenames)
            with self.assertRaisesRegex(RuntimeError, 'connection begin failed'):
                session.begin(150)
            run.close_snapshot_session()
            self.assertEqual([], protocol.calls)
            popen.assert_called_once()
            metadata = json.loads((directory / 'light-cold-start-baseline-readiness.json').read_text())
            self.assertFalse(metadata['passed'])
            self.assertEqual(110, metadata['session_begin']['deadline_monotonic_seconds'])
            self.assertEqual(100, metadata['session_begin']['finished_monotonic_seconds'])

    def test_home_window_state_requires_unique_matching_real_user_observations(self):
        for showing, expected in ((True, "locked"), (False, "unlocked")):
            with self.subTest(showing=showing):
                window = self.baseline_policy(showing) + self.baseline_window(showing=showing)
                state = home_window_state(window)
                self.assertEqual(expected, state["keyguard_state"])
                self.assertEqual(0, state["delegate_currentUser"])
                self.assertEqual([], state["unknown_reasons"])
                self.assertEqual("com.example.launcher/com.example.launcher.Home", state["focused_component"])
        locked = self.baseline_policy(True) + self.baseline_window(showing=True)
        unknown = [self.baseline_window(), self.baseline_policy(True, -10000) + self.baseline_window(showing=True),
                   self.baseline_policy(True) + self.baseline_window(),
                   self.baseline_policy(True, occluded=True) + self.baseline_window(showing=True),
                   locked + self.baseline_policy(True), locked + "isKeyguardShowing=true\n",
                   locked + "isKeyguardShowing=invalid\n"]
        for focus in ("invalid", "Window{second u0 com.other/.Home}",
                      "Window{abc u0 com.example.launcher/com.example.launcher.Home}"):
            unknown.append(locked + f"mCurrentFocus={focus}\n")
        unknown.extend([locked.replace("mCurrentFocus=Window{abc u0 com.example.launcher/com.example.launcher.Home}",
                                       "mCurrentFocus=invalid"),
                        locked.replace("mCurrentFocus=Window{abc u0 com.example.launcher/com.example.launcher.Home}\n", "")])
        for field, valid in (("showing", "true"), ("occluded", "false"), ("currentUser", "0")):
            unknown.extend([locked.replace(f"{field}={valid}", f"{field}=invalid", 1),
                            locked.replace(f"{field}={valid}", f"{field}={valid}\n      {field}=invalid", 1),
                            locked.replace(f"{field}={valid}", f"{field}={valid}\n      {field}={valid}", 1),
                            locked.replace(f"      {field}={valid}\n", "", 1)])
        unknown.append(locked.replace("currentUser=0", "currentUser=USER_NULL", 1))
        for window in unknown:
            with self.subTest(window=window):
                state = home_window_state(window)
                self.assertEqual("unknown", state["keyguard_state"])
                self.assertTrue(state["unknown_reasons"])
        real_null = locked.replace("Window{abc u0 com.example.launcher/com.example.launcher.Home}", "null")
        state = home_window_state(real_null)
        self.assertTrue(state["focus_valid"])
        self.assertEqual("null", state["current_focus"])
        self.assertIsNone(state["focused_component"])
        self.assertEqual("locked", state["keyguard_state"])
        real_shade = locked.replace("com.example.launcher/com.example.launcher.Home", "NotificationShade")
        self.assertEqual("locked", home_window_state(real_shade)["keyguard_state"])

    def test_home_ambiguous_focus_never_counts_a_launcher_match_as_stable(self):
        for extra in ("invalid", "Window{other u0 com.other/.Home}",
                      "Window{abc u0 com.example.launcher/com.example.launcher.Home}"):
            with self.subTest(extra=extra), tempfile.TemporaryDirectory() as temporary:
                run = SmokeRun(Path("app.apk"), Path(temporary), PACKAGE, None)
                self.prepare_baseline_reader(run)
                run.text = Mock(return_value="com.example.launcher/.Home\n")
                batch = self.baseline_batch(self.baseline_raw(), self.baseline_window() + f"mCurrentFocus={extra}\n")
                run.adb = self.baseline_adb(return_value=subprocess.CompletedProcess([], 0, batch, b""))
                clock = [0.0]
                with patch("android_ui_smoke.time.monotonic", side_effect=lambda: clock[0]), \
                        patch("android_ui_smoke.time.sleep", side_effect=lambda duration: clock.__setitem__(0, clock[0] + duration)), \
                        self.assertRaisesRegex(RuntimeError, "within 10s"):
                    run.wait_home_baseline("light-cold-start")
                metadata = json.loads((Path(temporary) / "light-cold-start-baseline-readiness.json").read_text())
                self.assertFalse(metadata["passed"])
                self.assertNotIn("keyguard_dismissal", metadata)
                self.assertTrue(all(sample["stable_captures"] == 0 for sample in metadata["samples"]))
                self.assertTrue(all(sample["window_state"]["focus_definition_count"] == 2 for sample in metadata["samples"]))

    def test_home_dismissal_exit_zero_needs_later_same_user_unlocked_and_three_fresh_captures(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            run = SmokeRun(Path("app.apk"), directory, PACKAGE, None)
            self.prepare_baseline_reader(run)
            clock = [0.0]
            events = []
            raw = self.baseline_raw()
            states = [(True, 0), (True, -10000), (False, 10), (False, 0), (False, 0), (False, 0)]
            run.text = Mock(return_value="com.example.launcher/.Home\n")
            def hierarchy(**kwargs):
                events.append("hierarchy")
                self.assertEqual(10, kwargs["deadline"])
                clock[0] += .2
                return self.baseline_hierarchy()
            def command(*args, **kwargs):
                self.assertGreater(kwargs["timeout"], 0)
                self.assertAlmostEqual(10 - clock[0], kwargs["timeout"])
                self.assertFalse(kwargs["check"])
                if args[3:] == ("dumpsys window policy && dumpsys window displays",):
                    events.append("initial")
                    clock[0] += .4
                    return subprocess.CompletedProcess([], 0,
                        (self.baseline_policy(True) + self.baseline_window(showing=True)).encode(), b"initial stderr")
                if args == ("shell", "wm", "dismiss-keyguard"):
                    events.append("dismiss")
                    clock[0] += .3
                    return subprocess.CompletedProcess([], 0, b"dismiss request stdout", b"dismiss stderr")
                events.append("capture")
                showing, user = states.pop(0)
                clock[0] += .5
                return subprocess.CompletedProcess([], 0, self.baseline_batch(raw,
                    self.baseline_window(showing=showing), self.baseline_policy(showing, user)), b"")
            run.snapshot_hierarchy = Mock(side_effect=hierarchy)
            run.adb = Mock(side_effect=command)
            with patch("android_ui_smoke.time.monotonic", side_effect=lambda: clock[0]), \
                    patch("android_ui_smoke.time.sleep", side_effect=lambda duration: clock.__setitem__(0, clock[0] + duration)):
                self.assertTrue(run.wait_home_baseline("light-cold-start").startswith(b"\x89PNG"))
            metadata = json.loads((directory / "light-cold-start-baseline-readiness.json").read_text())
            self.assertTrue(metadata["passed"])
            self.assertEqual([0, 0, 0, 1, 2, 3], [sample["stable_captures"] for sample in metadata["samples"]])
            self.assertEqual(["initial", "dismiss", "hierarchy", "capture"], events[:4])
            self.assertEqual(1, events.count("dismiss"))
            self.assertEqual(6, run.snapshot_hierarchy.call_count)
            self.assertEqual(6, len({sample["hierarchy"] for sample in metadata["samples"]}))
            dismissal = metadata["keyguard_dismissal"]
            self.assertTrue(dismissal["request_sent"])
            self.assertTrue(dismissal["completed"])
            self.assertEqual("sample-03", dismissal["completion_observation"])
            self.assertEqual("initial_window_state", dismissal["trigger_observation"])
            self.assertEqual(b"initial stderr", (directory / metadata["initial_window_state"]["stderr"]).read_bytes())
            self.assertEqual(b"dismiss request stdout", (directory / dismissal["stdout"]).read_bytes())
            self.assertLess(metadata["elapsed_seconds"], 10)

    def test_home_pending_dismissal_never_counts_locked_unknown_or_different_user_samples(self):
        for showing, user in ((True, 0), (True, -10000), (False, 10)):
            with self.subTest(showing=showing, user=user), tempfile.TemporaryDirectory() as temporary:
                run = SmokeRun(Path("app.apk"), Path(temporary), PACKAGE, None)
                self.prepare_baseline_reader(run)
                run.text = Mock(return_value="com.example.launcher/.Home\n")
                clock = [0.0]
                def command(*args, **kwargs):
                    self.assertAlmostEqual(10 - clock[0], kwargs["timeout"])
                    if args[3:] == ("dumpsys window policy && dumpsys window displays",):
                        return subprocess.CompletedProcess([], 0,
                            (self.baseline_policy(True) + self.baseline_window(showing=True)).encode(), b"")
                    if args == ("shell", "wm", "dismiss-keyguard"):
                        return subprocess.CompletedProcess([], 0, b"", b"")
                    clock[0] += min(.5, kwargs["timeout"])
                    return subprocess.CompletedProcess([], 0, self.baseline_batch(self.baseline_raw(),
                        self.baseline_window(showing=showing), self.baseline_policy(showing, user)), b"")
                run.adb = Mock(side_effect=command)
                with patch("android_ui_smoke.time.monotonic", side_effect=lambda: clock[0]), \
                        patch("android_ui_smoke.time.sleep", side_effect=lambda duration: clock.__setitem__(0, clock[0] + duration)), \
                        self.assertRaisesRegex(RuntimeError, "within 10s"):
                    run.wait_home_baseline("light-cold-start")
                metadata = json.loads((Path(temporary) / "light-cold-start-baseline-readiness.json").read_text())
                self.assertFalse(metadata["passed"])
                self.assertTrue(metadata["keyguard_dismissal"]["request_sent"])
                self.assertFalse(metadata["keyguard_dismissal"]["completed"])
                self.assertTrue(metadata["samples"])
                self.assertTrue(all(sample["stable_captures"] == 0 for sample in metadata["samples"]))
                self.assertEqual(1, sum(call.args == ("shell", "wm", "dismiss-keyguard") for call in run.adb.call_args_list))

    def test_home_unknown_start_state_never_requests_dismissal_or_replaces_original_content_gates(self):
        for has_content in (True, False):
            with self.subTest(has_content=has_content), tempfile.TemporaryDirectory() as temporary:
                run = SmokeRun(Path("app.apk"), Path(temporary), PACKAGE, None)
                self.prepare_baseline_reader(run)
                if not has_content:
                    run.snapshot_hierarchy = Mock(return_value=ET.fromstring('<hierarchy><node package="com.example.launcher" /></hierarchy>'))
                run.text = Mock(return_value="com.example.launcher/.Home\n")
                clock = [0.0]
                unknown_policy = self.baseline_policy(True, -10000)
                def command(*args, **kwargs):
                    self.assertNotEqual(("shell", "wm", "dismiss-keyguard"), args)
                    if args[3:] == ("dumpsys window policy && dumpsys window displays",):
                        return subprocess.CompletedProcess([], 0,
                            (unknown_policy + self.baseline_window(showing=True)).encode(), b"")
                    return subprocess.CompletedProcess([], 0, self.baseline_batch(self.baseline_raw(),
                        self.baseline_window(showing=True), unknown_policy), b"")
                run.adb = Mock(side_effect=command)
                with patch("android_ui_smoke.time.monotonic", side_effect=lambda: clock[0]), \
                        patch("android_ui_smoke.time.sleep", side_effect=lambda duration: clock.__setitem__(0, clock[0] + duration)):
                    if has_content:
                        run.wait_home_baseline("light-cold-start")
                    else:
                        with self.assertRaisesRegex(RuntimeError, "within 10s"):
                            run.wait_home_baseline("light-cold-start")
                metadata = json.loads((Path(temporary) / "light-cold-start-baseline-readiness.json").read_text())
                self.assertEqual(has_content, metadata["passed"])
                self.assertEqual("unknown", metadata["initial_window_state"]["state"]["keyguard_state"])
                self.assertNotIn("keyguard_dismissal", metadata)
                self.assertEqual(3, metadata["required_stable_captures"])
                self.assertTrue(all(sample["window_state"]["keyguard_state"] == "unknown" for sample in metadata["samples"]))

    def test_home_probe_error_and_partial_timeout_preserve_complete_streams_before_any_helper_read(self):
        for kind in ("nonzero", "timeout", "direct-timeout", "exception"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                run = SmokeRun(Path("app.apk"), Path(temporary), PACKAGE, None)
                self.prepare_baseline_reader(run)
                run.text = Mock(return_value="com.example.launcher/.Home\n")
                stdout, stderr = b"full probe stdout" * 500, b"full probe stderr" * 500
                def command(*args, **kwargs):
                    self.assertGreater(kwargs["timeout"], 0)
                    self.assertLessEqual(kwargs["timeout"], 10)
                    if kind == "nonzero":
                        return subprocess.CompletedProcess([], 7, stdout, stderr)
                    if kind == "exception":
                        raise OSError("probe spawn failed")
                    cause = subprocess.TimeoutExpired("adb", kwargs["timeout"], output=stdout, stderr=stderr)
                    if kind == "direct-timeout":
                        raise cause
                    raise RuntimeError("probe timed out") from cause
                run.adb = Mock(side_effect=command)
                with self.assertRaisesRegex(RuntimeError, "HOME baseline failed"):
                    run.wait_home_baseline("light-cold-start")
                metadata = json.loads((Path(temporary) / "light-cold-start-baseline-readiness.json").read_text())
                probe = metadata["initial_window_state"]
                self.assertFalse(metadata["passed"])
                self.assertEqual([], metadata["samples"])
                run.snapshot_hierarchy.assert_not_called()
                self.assertEqual(stdout if kind != "exception" else b"", (Path(temporary) / probe["stdout"]).read_bytes())
                self.assertEqual(stderr if kind != "exception" else b"", (Path(temporary) / probe["stderr"]).read_bytes())
                self.assertIn("started_monotonic_seconds", probe)
                self.assertIn("ended_monotonic_seconds", probe)
                if "timeout" in kind:
                    self.assertTrue(probe["partial_streams"])
                    self.assertEqual("timed-out", probe["outcome"])

    def test_home_late_probe_or_dismissal_cannot_start_helper_or_pass(self):
        for late_stage in ("probe", "dismiss", "probe-persistence"):
            with self.subTest(late_stage=late_stage), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                run = SmokeRun(Path("app.apk"), directory, PACKAGE, None)
                self.prepare_baseline_reader(run)
                run.text = Mock(return_value="com.example.launcher/.Home\n")
                clock = [0.0]
                def command(*args, **kwargs):
                    self.assertAlmostEqual(10 - clock[0], kwargs["timeout"])
                    if args[3:] == ("dumpsys window policy && dumpsys window displays",):
                        clock[0] = 10.001 if late_stage == "probe" else 1
                        return subprocess.CompletedProcess([], 0,
                            (self.baseline_policy(True) + self.baseline_window(showing=True)).encode(), b"real probe stderr")
                    self.assertEqual(("shell", "wm", "dismiss-keyguard"), args)
                    clock[0] = 10.001
                    return subprocess.CompletedProcess([], 0, b"real dismiss stdout", b"real dismiss stderr")
                original_write = Path.write_bytes
                def persist(path, data):
                    result = original_write(path, data)
                    if late_stage == "probe-persistence" and path.name.endswith("initial_window_state-stderr.bin"):
                        clock[0] = 10.001
                    return result
                run.adb = Mock(side_effect=command)
                with patch("android_ui_smoke.time.monotonic", side_effect=lambda: clock[0]), \
                        patch.object(Path, "write_bytes", autospec=True, side_effect=persist), \
                        self.assertRaisesRegex(RuntimeError, "within 10s"):
                    run.wait_home_baseline("light-cold-start")
                metadata = json.loads((directory / "light-cold-start-baseline-readiness.json").read_text())
                self.assertFalse(metadata["passed"])
                self.assertEqual(10.001, metadata["elapsed_seconds"])
                self.assertEqual([], metadata["samples"])
                run.snapshot_hierarchy.assert_not_called()
                self.assertEqual(b"real probe stderr", (directory / metadata["initial_window_state"]["stderr"]).read_bytes())
                if late_stage == "dismiss":
                    dismissal = metadata["keyguard_dismissal"]
                    self.assertTrue(dismissal["request_sent"])
                    self.assertFalse(dismissal["completed"])
                    self.assertEqual(9, dismissal["timeout_seconds"])
                    self.assertEqual(b"real dismiss stdout", (directory / dismissal["stdout"]).read_bytes())
                else:
                    self.assertNotIn("keyguard_dismissal", metadata)

    def test_home_failed_or_timed_out_dismissal_keeps_trigger_partial_evidence_and_original_error(self):
        for kind in ("nonzero", "timeout"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                run = SmokeRun(Path("app.apk"), directory, PACKAGE, None)
                self.prepare_baseline_reader(run)
                run.text = Mock(return_value="com.example.launcher/.Home\n")
                stdout, stderr = b"dismiss output" * 500, b"dismiss error" * 500
                def command(*args, **kwargs):
                    if args[3:] == ("dumpsys window policy && dumpsys window displays",):
                        return subprocess.CompletedProcess([], 0,
                            (self.baseline_policy(True) + self.baseline_window(showing=True)).encode(), b"")
                    self.assertEqual(("shell", "wm", "dismiss-keyguard"), args)
                    if kind == "nonzero":
                        return subprocess.CompletedProcess([], 9, stdout, stderr)
                    cause = subprocess.TimeoutExpired("adb", kwargs["timeout"], output=stdout, stderr=stderr)
                    raise RuntimeError("actual dismissal timed out") from cause
                run.adb = Mock(side_effect=command)
                expected_error = "dismissal failed" if kind == "nonzero" else "actual dismissal timed out"
                with self.assertRaisesRegex(RuntimeError, expected_error):
                    run.wait_home_baseline("light-cold-start")
                metadata = json.loads((directory / "light-cold-start-baseline-readiness.json").read_text())
                dismissal = metadata["keyguard_dismissal"]
                self.assertFalse(metadata["passed"])
                self.assertFalse(dismissal["completed"])
                self.assertFalse(dismissal["request_sent"])
                self.assertEqual("initial_window_state", dismissal["trigger_observation"])
                self.assertEqual("locked", dismissal["trigger_state"]["keyguard_state"])
                self.assertEqual(stdout, (directory / dismissal["stdout"]).read_bytes())
                self.assertEqual(stderr, (directory / dismissal["stderr"]).read_bytes())
                run.snapshot_hierarchy.assert_not_called()

    def test_home_probe_or_dismissal_evidence_failure_is_fatal_and_does_not_replace_rpc_timeout(self):
        for stage in ("initial_window_state", "keyguard_dismissal"):
            for timeout in (False, True):
                with self.subTest(stage=stage, timeout=timeout), tempfile.TemporaryDirectory() as temporary:
                    directory = Path(temporary)
                    run = SmokeRun(Path("app.apk"), directory, PACKAGE, None,
                                   record_launch=True, visual_launch_only=True)
                    self.prepare_baseline_reader(run)
                    run.text = Mock(return_value="com.example.launcher/.Home\n")
                    run.begin_launch_recording = Mock()
                    run.launch_and_capture = Mock()
                    def command(*args, **kwargs):
                        is_probe = args[3:] == ("dumpsys window policy && dumpsys window displays",)
                        current_stage = "initial_window_state" if is_probe else "keyguard_dismissal"
                        if timeout and current_stage == stage:
                            cause = subprocess.TimeoutExpired("adb", kwargs["timeout"], output=b"partial stdout", stderr=b"partial stderr")
                            raise RuntimeError("original RPC timeout") from cause
                        return subprocess.CompletedProcess([], 0,
                            (self.baseline_policy(True) + self.baseline_window(showing=True)).encode() if is_probe else b"request stdout",
                            b"real stderr")
                    original_write = Path.write_bytes
                    def persist(path, data):
                        if path.name.endswith(f"{stage}-stderr.bin"):
                            raise OSError("baseline evidence write failed")
                        return original_write(path, data)
                    run.adb = Mock(side_effect=command)
                    with patch.object(Path, "write_bytes", autospec=True, side_effect=persist), \
                            self.assertRaisesRegex(RuntimeError, "original RPC timeout" if timeout else "baseline evidence write failed") as failure:
                        run.launch("light-cold-start")
                    metadata = json.loads((directory / "light-cold-start-baseline-readiness.json").read_text())
                    self.assertFalse(metadata["passed"])
                    self.assertEqual([], metadata["samples"])
                    self.assertIn("baseline evidence write failed", metadata[stage]["persistence_error"])
                    self.assertIn("persistence_finished_elapsed_seconds", metadata[stage])
                    if timeout:
                        self.assertIsInstance(failure.exception.__cause__.__cause__, subprocess.TimeoutExpired)
                        self.assertEqual(b"partial stdout", (directory / metadata[stage]["stdout"]).read_bytes())
                    run.snapshot_hierarchy.assert_not_called()
                    run.begin_launch_recording.assert_not_called()
                    run.launch_and_capture.assert_not_called()

    def test_home_later_valid_locked_sample_requests_only_one_dismissal_within_same_deadline(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            run = SmokeRun(Path("app.apk"), directory, PACKAGE, None)
            self.prepare_baseline_reader(run)
            run.text = Mock(return_value="com.example.launcher/.Home\n")
            clock = [0.0]
            capture_index = [0]
            def command(*args, **kwargs):
                self.assertAlmostEqual(10 - clock[0], kwargs["timeout"])
                if args[3:] == ("dumpsys window policy && dumpsys window displays",):
                    return subprocess.CompletedProcess([], 0,
                        (self.baseline_policy(True, -10000) + self.baseline_window(showing=True)).encode(), b"")
                if args == ("shell", "wm", "dismiss-keyguard"):
                    self.assertEqual(1, capture_index[0])
                    self.assertGreater(clock[0], 0)
                    clock[0] += .3
                    return subprocess.CompletedProcess([], 0, b"request sent", b"")
                showing = capture_index[0] == 0
                capture_index[0] += 1
                clock[0] += .5
                return subprocess.CompletedProcess([], 0, self.baseline_batch(self.baseline_raw(),
                    self.baseline_window(showing=showing), self.baseline_policy(showing)), b"")
            run.adb = Mock(side_effect=command)
            with patch("android_ui_smoke.time.monotonic", side_effect=lambda: clock[0]), \
                    patch("android_ui_smoke.time.sleep", side_effect=lambda duration: clock.__setitem__(0, clock[0] + duration)):
                run.wait_home_baseline("light-cold-start")
            metadata = json.loads((directory / "light-cold-start-baseline-readiness.json").read_text())
            self.assertTrue(metadata["passed"])
            self.assertEqual([0, 1, 2, 3], [sample["stable_captures"] for sample in metadata["samples"]])
            self.assertEqual("sample-00", metadata["keyguard_dismissal"]["trigger_observation"])
            self.assertEqual("sample-01", metadata["keyguard_dismissal"]["completion_observation"])
            self.assertEqual(4, run.snapshot_hierarchy.call_count)
            self.assertEqual(1, sum(call.args == ("shell", "wm", "dismiss-keyguard") for call in run.adb.call_args_list))

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
            run.adb = self.baseline_adb(side_effect=[subprocess.CompletedProcess([], 0, self.baseline_batch(png), b"") for png in captures])
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
            self.assertEqual(5, run.adb.call_count)
            for call, png in zip(run.adb.call_args_list[1:], captures):
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
            self.assertEqual(5, run.adb.call_count)  # No competing uiautomator connection.

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
                run.adb = self.baseline_adb(side_effect=capture)
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
            run.adb = self.baseline_adb(side_effect=capture)
            with patch("android_ui_smoke.time.monotonic", side_effect=lambda: clock[0]), \
                    patch("android_ui_smoke.time.sleep", side_effect=lambda duration: clock.__setitem__(0, clock[0] + duration)):
                png = run.wait_home_baseline("light-cold-start")
                self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertEqual(4, run.adb.call_count)
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
                run.adb = self.baseline_adb(return_value=subprocess.CompletedProcess([], 0, raw, b""))
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
            run.adb = self.baseline_adb(side_effect=timeout)
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
            run.adb = self.baseline_adb(return_value=subprocess.CompletedProcess([], 0, batch, b"capture stderr"))
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
            run.adb = self.baseline_adb(side_effect=capture)
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
            run.adb = self.baseline_adb(return_value=subprocess.CompletedProcess([], 0, batch, b""))
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
                run.adb = self.baseline_adb(return_value=subprocess.CompletedProcess(
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
            run.adb = self.baseline_adb(return_value=subprocess.CompletedProcess([], 0, self.baseline_batch(raw), b""))
            with patch("android_ui_smoke.time.sleep"):
                run.wait_home_baseline("light-cold-start")
            command = run.adb.call_args.args[3]
            binaries = directory / "bin"
            binaries.mkdir()
            dumpsys = binaries / "dumpsys"
            dumpsys.write_text(f"#!{sys.executable}\nimport sys\nsys.stdout.buffer.write("
                               f"{self.baseline_policy().encode()!r} if sys.argv[-1]=='policy' else {self.baseline_window().encode()!r})\n")
            dumpsys.chmod(0o755)
            screencap = binaries / "screencap"
            for exit_code in (0, 7):
                screencap.write_text(f"#!{sys.executable}\nimport sys\nsys.stdout.buffer.write({raw!r})\nsys.exit({exit_code})\n")
                screencap.chmod(0o755)
                environment = {**os.environ, "PATH": str(binaries) + os.pathsep + os.environ["PATH"]}
                result = subprocess.run(["bash", "-c", command], env=environment, capture_output=True, timeout=5)
                self.assertEqual(exit_code, result.returncode)
                window, compressed = result.stdout.split(b"\x00LUOSHU_HOME_BASELINE_RAW_GZIP\x00")
                self.assertEqual((self.baseline_policy() + self.baseline_window()).encode(), window)
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
            root = ET.fromstring(f'''<hierarchy rotation="0"><node package="{PACKAGE}" bounds="[0,0][1080,1920]">
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


class LibraryEmptyManagementHarnessTest(unittest.TestCase):
    """Controlled host windows test gestures and reveal failures, not device pixels."""
    def library(self, phase, *, import_state="disabled", entry_state="whole", selected="字体库"):
        root = ET.fromstring(f'''<hierarchy rotation="0">
          <node package="{PACKAGE}" bounds="[0,0][1080,1920]">
            <node package="{PACKAGE}" scrollable="true" bounds="[0,63][1080,1920]" />
            <node resource-id="android:id/navigationBarBackground" bounds="[0,1840][1080,1920]" />
          </node>
        </hierarchy>''')
        content = root[0][0]

        def text(label, rectangle):
            return ET.SubElement(content, "node", {"package": PACKAGE, "text": label, "bounds": rectangle})

        def button(label, rectangle, *, enabled=True, selected=False, label_bounds=None):
            target = ET.SubElement(content, "node", {"package": PACKAGE, "enabled": str(enabled).lower(),
                "selected": str(selected).lower(), "focusable": str(enabled).lower(),
                "clickable": str(not selected).lower(), "bounds": rectangle})
            left, top, right, bottom = bounds(target)
            ET.SubElement(target, "node", {"package": PACKAGE, "text": label, "enabled": "true",
                "bounds": label_bounds or f"[{left + 20},{top + 20}][{right - 20},{bottom - 20}]"})
            return target

        if phase == "top":
            button("搜索你的字体", "[40,260][1040,410]", label_bounds="[160,300][420,360]")
            button("全部", "[40,420][200,550]", selected=True)
            button("导入与管理", "[780,740][1040,870]")
            text("从第一款字体开始", "[320,1100][760,1170]")
            button("打开导入与管理", "[260,2200][820,2330]")
        elif phase == "entry":
            text("从第一款字体开始", "[320,1100][760,1170]")
            if entry_state != "missing":
                rectangle = "[260,1400][820,1530]" if entry_state in ("whole", "partial-label") else "[260,1640][820,1790]"
                label_bounds = "[300,1450][780,1550]" if entry_state == "partial-label" else None
                button("打开导入与管理", rectangle, label_bounds=label_bounds)
        elif phase == "revealed":
            button("收起管理", "[780,150][1040,280]")
            if import_state != "missing":
                rectangle = "[220,350][1020,490]"
                if import_state in ("dock", "partial-control"):
                    rectangle = "[220,1710][1020,1850]" if import_state == "dock" else "[220,1640][1020,1780]"
                label_bounds = "[400,1650][800,1680]" if import_state == "partial-control" else \
                    "[400,400][800,520]" if import_state == "partial-label" else None
                button("导入字体", rectangle, enabled=import_state == "enabled", label_bounds=label_bounds)
        elif phase == "closed":
            button("导入与管理", "[780,150][1040,280]")
        else:
            raise AssertionError(phase)
        dock = ET.SubElement(root[0], "node", {"package": PACKAGE, "bounds": "[60,1700][1020,1840]"})
        for index, label in enumerate(("首页", "字体库", "组合", "设置")):
            left = 60 + index * 240
            target = ET.SubElement(dock, "node", {"package": PACKAGE, "enabled": "true", "focusable": "true",
                "selected": str(label == selected).lower(), "clickable": str(label != selected).lower(),
                "bounds": f"[{left},1700][{left + 240},1840]"})
            ET.SubElement(target, "node", {"package": PACKAGE, "text": label,
                "bounds": f"[{left + 40},1760][{left + 200},1810]"})
        return root

    def prepare(self, output, *, import_state="disabled", entry_state="whole", selected="字体库",
                restore=True, transient=False):
        from PIL import Image
        png = io.BytesIO()
        Image.new("RGB", (540, 960), "gray").save(png, format="PNG")
        run = SmokeRun(Path("app.apk"), output, PACKAGE, None)
        clock = [0.0]
        state = {"phase": "top", "taps": 0, "post_tap_swipes": 0, "closed": False, "reads": 0}
        top = self.library("top")
        entry = self.library("entry", entry_state=entry_state)
        revealed = self.library("revealed", import_state=import_state, selected=selected)
        closed = self.library("closed")
        current = [top]

        def adb(*args, **kwargs):
            if args[:3] == ("shell", "input", "swipe"):
                if state["taps"] and not state["closed"]:
                    state["post_tap_swipes"] += 1
                    raise AssertionError("A test swipe must never reveal the tools after the entry tap")
                current[0] = top if state["closed"] and restore else closed if state["closed"] else entry
                clock[0] += 2
            elif args[:3] == ("shell", "input", "tap"):
                state["taps"] += 1
                if state["taps"] == 1:
                    self.assertEqual(center(visible_action(entry, "打开导入与管理", PACKAGE)),
                                     (int(args[3]), int(args[4])))
                    state["phase"] = "revealed"
                    current[0] = revealed
                else:
                    self.assertEqual(center(visible_action(revealed, "收起管理", PACKAGE)),
                                     (int(args[3]), int(args[4])))
                    state["closed"] = True
                    current[0] = closed
            return subprocess.CompletedProcess([], 0, png.getvalue() if args[:2] == ("exec-out", "screencap") else b"", b"")

        def hierarchy():
            if transient and state["phase"] == "revealed" and not state["closed"]:
                state["reads"] += 1
                if state["reads"] == 1:
                    return entry  # Expansion can precede the App's next-frame scroll.
            return current[0]

        run.adb = Mock(side_effect=adb)
        run.hierarchy = Mock(side_effect=hierarchy)
        run.text = Mock(return_value="Physical size: 1440x3120\nOverride size: 1080x1920\n")
        run.assert_running = Mock()
        run.select_tab = Mock(return_value=top)
        run.scroll = Mock(side_effect=AssertionError("Use bounded measured searches, never blind scroll"))
        run.ensure_dock = Mock(side_effect=AssertionError("A post-tap dock gesture would mask the reveal failure"))
        return run, clock, state

    def exercise(self, run, clock):
        with patch("android_ui_smoke.time.monotonic", side_effect=lambda: clock[0]), \
                patch("android_ui_smoke.time.sleep", side_effect=lambda seconds: clock.__setitem__(0, clock[0] + seconds)):
            run.verify_library_empty_management_reveal()

    def test_disabled_import_passes_with_real_search_taps_captures_and_downward_reset(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            run, clock, state = self.prepare(output)
            self.exercise(run, clock)
            self.assertEqual((2, 0, True), (state["taps"], state["post_tap_swipes"], state["closed"]))
            self.assertEqual(1, len(run.checks))
            self.assertEqual("library-empty-management-reveal", run.checks[0]["check"])
            self.assertEqual("false", run.checks[0]["import_enabled"])
            self.assertEqual(0, run.checks[0]["post_tap_test_scrolls"])
            run.select_tab.assert_called_once_with("字体库", "搜索你的字体")
            for name in ("before-tap", "after-tap", "restored-top"):
                prefix = output / f"library-empty-management-{name}"
                self.assertTrue(prefix.with_suffix(".png").read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))
                self.assertTrue(prefix.with_suffix(".xml").is_file())
            after = ET.parse(output / "library-empty-management-after-tap.xml").getroot()
            self.assertTrue(action_disabled(after, "导入字体", PACKAGE))
            self.assertEqual((220, 350, 1020, 490), bounds(visible_control(after, "导入字体", PACKAGE)))
            searches = [json.loads((output / f"scroll-search-{number:04d}.json").read_text()) for number in (1, 2)]
            self.assertEqual([("up", 5, 1), ("down", 8, 1)],
                             [(item["direction"], item["max_gestures"], item["gestures_used"]) for item in searches])
            self.assertTrue(all(item["passed"] for item in searches))
            swipes = [call.args for call in run.adb.call_args_list if call.args[:3] == ("shell", "input", "swipe")]
            self.assertGreater(int(swipes[0][4]), int(swipes[0][6]))
            self.assertLess(int(swipes[1][4]), int(swipes[1][6]))
            restored = ET.parse(output / "library-empty-management-restored-top.xml").getroot()
            self.assertTrue(page_ready(restored, "字体库", "搜索你的字体", PACKAGE))
            self.assertTrue(choice_selected(restored, "全部", PACKAGE))
            self.assertNotIn("收起管理", app_labels(restored, PACKAGE))
            run.scroll.assert_not_called()
            run.ensure_dock.assert_not_called()

    def test_enabled_import_and_delayed_app_reveal_pass_without_a_post_tap_swipe(self):
        with tempfile.TemporaryDirectory() as temporary:
            run, clock, state = self.prepare(Path(temporary), import_state="enabled", transient=True)
            self.exercise(run, clock)
            self.assertGreaterEqual(state["reads"], 2)
            self.assertEqual(0, state["post_tap_swipes"])
            self.assertEqual("true", run.checks[0]["import_enabled"])

    def test_missing_dock_occluded_and_partial_import_fail_and_keep_the_last_xml_and_png(self):
        for import_state in ("missing", "dock", "partial-control", "partial-label"):
            with self.subTest(import_state=import_state), tempfile.TemporaryDirectory() as temporary:
                output = Path(temporary)
                run, clock, state = self.prepare(output, import_state=import_state)
                with self.assertRaisesRegex(RuntimeError, "without a test scroll did not become ready"):
                    self.exercise(run, clock)
                self.assertEqual((1, 0, False), (state["taps"], state["post_tap_swipes"], state["closed"]))
                self.assertEqual([], run.checks)
                self.assertTrue((output / "library-empty-management-after-tap.png").is_file())
                actual = ET.parse(output / "library-empty-management-after-tap.xml").getroot()
                self.assertEqual(ET.tostring(self.library("revealed", import_state=import_state)), ET.tostring(actual))
                self.assertEqual(1, len(list(output.glob("scroll-search-*.json"))))
                run.ensure_dock.assert_not_called()
                run.scroll.assert_not_called()

    def test_selected_page_and_whole_collapse_control_are_required(self):
        for invalid in ("wrong-page", "missing-collapse", "occluded-collapse"):
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory() as temporary:
                run, clock, state = self.prepare(Path(temporary), selected="设置" if invalid == "wrong-page" else "字体库")
                original = run.hierarchy.side_effect
                def hierarchy():
                    root = original()
                    if state["phase"] == "revealed" and invalid != "wrong-page":
                        content = scroll_content(root, PACKAGE)[0]
                        toggle = next((node for node in content if "收起管理" in app_labels(node, PACKAGE)), None)
                        if toggle is None:
                            return root
                        if invalid == "missing-collapse":
                            content.remove(toggle)
                        else:
                            toggle.set("bounds", "[780,1640][1040,1780]")
                    return root
                run.hierarchy = Mock(side_effect=hierarchy)
                with self.assertRaisesRegex(RuntimeError, "did not become ready"):
                    self.exercise(run, clock)
                self.assertEqual([], run.checks)
                self.assertEqual(0, state["post_tap_swipes"])

    def test_missing_or_partial_empty_entry_is_never_tapped(self):
        for entry_state in ("missing", "dock", "partial-label"):
            with self.subTest(entry_state=entry_state), tempfile.TemporaryDirectory() as temporary:
                run, clock, state = self.prepare(Path(temporary), entry_state=entry_state)
                with self.assertRaisesRegex(RuntimeError, "stalled or reached a boundary"):
                    self.exercise(run, clock)
                self.assertEqual(0, state["taps"])
                self.assertEqual([], run.checks)
                self.assertEqual([], run.results)
                evidence = json.loads((Path(temporary) / "scroll-search-0001.json").read_text())
                self.assertFalse(evidence["passed"])
                self.assertLessEqual(evidence["gestures_used"], 5)

    def test_restore_failure_does_not_skip_the_downward_search_or_capture_a_restored_top(self):
        for restore in ("missing-search", "partial-search"):
            with self.subTest(restore=restore), tempfile.TemporaryDirectory() as temporary:
                run, clock, state = self.prepare(Path(temporary), restore=restore == "partial-search")
                if restore == "partial-search":
                    original = run.hierarchy.side_effect
                    def hierarchy():
                        root = original()
                        if state["closed"] and "搜索你的字体" in app_labels(root, PACKAGE):
                            field = label_target(root, "搜索你的字体", PACKAGE)
                            field.set("bounds", "[40,0][1040,410]")
                            self.assertTrue(visible_text(root, "搜索你的字体", PACKAGE))
                        return root
                    run.hierarchy = Mock(side_effect=hierarchy)
                with self.assertRaisesRegex(RuntimeError, "stalled or reached a boundary"):
                    self.exercise(run, clock)
                self.assertTrue(state["closed"])
                self.assertEqual(1, len(run.checks))
                self.assertFalse((Path(temporary) / "library-empty-management-restored-top.xml").exists())
                evidence = json.loads((Path(temporary) / "scroll-search-0002.json").read_text())
                self.assertEqual("down", evidence["direction"])
                self.assertFalse(evidence["passed"])

    def test_ordinary_smoke_calls_empty_reveal_before_the_unchanged_preservation_phase(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = SmokeRun(Path("app.apk"), Path(temporary), PACKAGE, None)
            root = UiSmokeHarnessTest().hierarchy()
            mode = ["no"]
            order = []
            def adb(*args, **kwargs):
                if args[:4] == ("shell", "cmd", "uimode", "night"):
                    mode[0] = args[4]
            run.adb = Mock(side_effect=adb)
            run.text = Mock(side_effect=lambda *args, **kwargs: "36" if args[-1] == "ro.build.version.sdk"
                            else f"Night mode: {mode[0]}")
            run.hierarchy = Mock(return_value=root)
            run.wait_page = Mock(return_value=root)
            run.wait_ui = Mock(return_value=root)
            run.launch = Mock()
            run.capture = Mock()
            run.logcat = Mock()
            run.record = Mock()
            run.select_tab = Mock()
            run.assert_running = Mock()
            for method in ("verify_rapid_navigation", "verify_settings_details", "verify_library_empty_management_reveal",
                           "verify_library_preservation", "verify_disabled_animations"):
                setattr(run, method, Mock(side_effect=lambda name=method: order.append(name)))
            with patch("android_ui_smoke.time.sleep"):
                run.run()
            self.assertEqual(["verify_rapid_navigation", "verify_settings_details", "verify_library_empty_management_reveal",
                              "verify_library_preservation", "verify_disabled_animations"], order)

    def test_visual_only_run_never_enters_the_new_functional_reveal(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = SmokeRun(Path("app.apk"), Path(temporary), PACKAGE, None, record_launch=True, visual_launch_only=True)
            run.adb = Mock()
            run.text = Mock(return_value="36")
            run.launch = Mock()
            run.assert_running = Mock()
            run.verify_library_empty_management_reveal = Mock(side_effect=AssertionError("Functional reveal is a separate run"))
            run.run()
            run.verify_library_empty_management_reveal.assert_not_called()


class LibraryRestorationHarnessTest(unittest.TestCase):
    """Replay the retained failure and controlled variants; no device PASS is claimed."""
    def fixture(self, name):
        return ET.parse(Path(__file__).parent / f"ui_smoke_fixtures/api28-{name}-991c0320.xml").getroot()

    def library(self, offset=0, *, favorite=None, search=False):
        # Controlled host variants of the complete recorded main-content tree.
        # Header bounds/selected-parent semantics are reduced from the same
        # failed run's library-favorite-filter.xml; these are not new device dumps.
        root = self.fixture("library-return")
        content, _ = scroll_content(root, PACKAGE)
        for node in content.iter("node"):
            if node is content:
                continue
            try:
                left, top, right, bottom = bounds(node)
            except ValueError:
                continue
            node.set("bounds", f"[{left},{top + offset}][{right},{bottom + offset}]")
        ET.SubElement(content, "node", {"package": PACKAGE, "text": "筛选结果",
            "bounds": "[47,612][223,677]"})
        if favorite is not None:
            chip = ET.SubElement(content, "node", {"package": PACKAGE, "enabled": "true",
                "focusable": "true", "selected": "true" if favorite else "false",
                "clickable": "false" if favorite else "true", "bounds": "[205,442][397,569]"})
            ET.SubElement(chip, "node", {"package": PACKAGE, "text": "收藏", "bounds": "[292,486][360,526]"})
        if search:
            ET.SubElement(content, "node", {"package": PACKAGE, "text": "搜索你的字体",
                "bounds": "[179,306][413,367]"})
        return root

    def prepare(self, output, snapshots, *, clock=None, background_delay=0):
        run = SmokeRun(Path("app.apk"), output, PACKAGE, None)
        scrolled = self.fixture("library-return")
        expanded = self.library(offset=100)
        ET.SubElement(scroll_content(expanded, PACKAGE)[0], "node", {"package": PACKAGE,
            "text": "收起管理", "bounds": "[50,500][400,580]"})
        run.adb = Mock(side_effect=lambda *args, **kwargs: clock.__setitem__(0, clock[0] + 10)
                       if clock is not None and args[:3] == ("shell", "input", "swipe") else None)
        run.assert_running = Mock()
        run.hierarchy = Mock(side_effect=snapshots)
        run.select_tab = Mock()
        run.tap_label = Mock()
        run.ensure_dock = Mock(return_value=scrolled)
        run.capture = Mock()
        run.record = Mock()
        run.scroll = Mock(side_effect=AssertionError("Restoration must use measured reach_content, not blind 400ms drags"))

        def text(*args, **kwargs):
            if args == ("shell", "wm", "size"):
                return "Physical size: 1440x3120\nOverride size: 1080x1920\n"
            raise StopIteration("Restoration completed before the rotation stage")
        run.text = Mock(side_effect=text)

        def wait(predicate, description, **kwargs):
            if description == "Favorite library filter":
                current = self.library(favorite=True)
            elif description == "Expanded production font management tools":
                current = expanded
            elif description == "Font library scroll position after leaving and returning to its tab":
                current = scrolled
            elif description == "Library page, filter and scroll position on returning from the background":
                current = next(call.args[1] for call in run.capture.call_args_list
                               if call.args[0] == "library-filter-after-tab")
                if clock is not None:
                    clock[0] += background_delay
            else:
                raise AssertionError(f"Unexpected wait: {description}")
            self.assertTrue(predicate(current), description)
            return current
        run.wait_ui = Mock(side_effect=wait)

        reach = run.reach_content
        def replay(predicate, description, **kwargs):
            # The pre-existing up-scroll coverage verifies the earlier phase.
            # Replay only its result here; both changed restoration calls run
            # the production reach_content with the actual retained tree.
            if description == "Font library real scroll below expanded management rows":
                return scrolled
            return reach(predicate, description, **kwargs)
        run.reach_content = Mock(side_effect=replay)
        return run

    def checks(self, run):
        return [call.args[0] for call in run.record.call_args_list]

    def swipes(self, run):
        return [call for call in run.adb.call_args_list if call.args[:3] == ("shell", "input", "swipe")]

    def test_retained_api28_snapshots_match_provenance_and_portrait_modal_geometry(self):
        directory = Path(__file__).parent / "ui_smoke_fixtures"
        source = json.loads((directory / "api28-family-modal-991c0320.source.json").read_text())
        self.assertEqual("991c0320e2575d551127a1ab5c2067fb8963ed1b", source["sourceCommit"])
        self.assertEqual(37702305934, source["sourceWorkflowRun"])
        for member in source["sourceMembers"]:
            raw = (directory / member["fixtureFile"]).read_bytes()
            self.assertEqual(member["fixtureBytes"], len(raw))
            self.assertEqual(member["fixtureSha256"], hashlib.sha256(raw).hexdigest())
        modal = self.fixture("family-modal")
        self.assertEqual("0", modal.get("rotation"))
        window = app_window_bounds(modal, PACKAGE)
        self.assertEqual((120, 622, 960, 1234), window)
        self.assertGreater(window[2] - window[0], window[3] - window[1])
        self.assertEqual((1080, 1920), logical_input_size(
            "Physical size: 1440x3120\nOverride size: 1080x1920\n", window, modal))
        self.assertIn("Family 与收藏管理", app_labels(modal, PACKAGE))
        self.assertFalse(page_ready(modal, "字体库", "搜索你的字体", PACKAGE))
        self.assertFalse(choice_selected(modal, "收藏", PACKAGE))

    def test_complete_snapshot_rotation_controls_all_four_input_orientations(self):
        # 0 is retained device evidence; 1/2/3 are explicit host metadata variants.
        # A square/portrait-shaped dialog must never choose the display rotation.
        for rotation, expected in (("0", (1080, 1920)), ("1", (1920, 1080)),
                                   ("2", (1080, 1920)), ("3", (1920, 1080))):
            with self.subTest(rotation=rotation):
                root = self.fixture("family-modal")
                root.set("rotation", rotation)
                self.assertEqual(expected, logical_input_size(
                    "Physical size: 1440x3120\nOverride size: 1080x1920\n", (120, 200, 800, 900), root))
                self.assertEqual((expected[0] * 2, expected[1] * 2), logical_input_size(
                    "Physical size: 2160x3840\n", (120, 200, 800, 900), root))

    def test_unknown_rotation_partial_snapshot_and_outside_window_refuse_both_scroll_paths(self):
        for invalid in (None, "", "4", "-1", "90", "unknown", " 0 ", "0.0", "partial", "outside"):
            for path in ("scroll", "reach_content"):
                with self.subTest(rotation=invalid, path=path), tempfile.TemporaryDirectory() as temporary:
                    root = self.fixture("library-return")
                    if invalid is None:
                        root.attrib.pop("rotation")
                    elif invalid == "partial":
                        root.tag = "node"
                    elif invalid == "outside":
                        next(node for node in root.iter("node") if node.get("package") == PACKAGE).set(
                            "bounds", "[0,0][1440,3120]")
                    else:
                        root.set("rotation", invalid)
                    run = SmokeRun(Path("app.apk"), Path(temporary), PACKAGE, None)
                    run.adb = Mock()
                    run.text = Mock(return_value="Physical size: 1440x3120\nOverride size: 1080x1920\n")
                    run.assert_running = Mock()
                    error = "exceeds logical input" if invalid == "outside" else "actual display rotation"
                    with self.assertRaisesRegex(RuntimeError, error):
                        if path == "scroll":
                            run.scroll(root, "down")
                        else:
                            run.reach_content(lambda current: True, "invalid snapshot", root=root)
                    run.adb.assert_not_called()
                    if path == "reach_content":
                        evidence = json.loads((Path(temporary) / "scroll-search-0001.json").read_text())
                        self.assertFalse(evidence["passed"])
                        self.assertEqual(0, evidence["gestures_used"])

    def test_original_family_modal_has_no_vertical_content_and_never_receives_a_gesture(self):
        modal = self.fixture("family-modal")
        for path in ("scroll", "reach_content"):
            with self.subTest(path=path), tempfile.TemporaryDirectory() as temporary:
                run = SmokeRun(Path("app.apk"), Path(temporary), PACKAGE, None)
                run.adb = Mock()
                run.text = Mock(return_value="Physical size: 1440x3120\nOverride size: 1080x1920\n")
                with self.assertRaisesRegex(RuntimeError, "No visible vertical App scroll container"):
                    if path == "scroll":
                        run.scroll(modal, "down")
                    else:
                        run.reach_content(lambda current: True, "modal cannot pass", root=modal)
                run.adb.assert_not_called()
                if path == "reach_content":
                    evidence = json.loads((Path(temporary) / "scroll-search-0001.json").read_text())
                    self.assertFalse(evidence["passed"])
                    self.assertEqual(0, evidence["gestures_used"])
                    self.assertEqual(ET.tostring(modal), ET.tostring(
                        ET.parse(Path(temporary) / "scroll-search-0001-000.xml").getroot()))

    def test_library_restoration_measures_progress_and_keeps_separate_original_phase_budgets(self):
        with tempfile.TemporaryDirectory() as temporary:
            moving = self.library(offset=80)
            favorite = self.library(offset=200, favorite=True)
            ready = self.library(offset=220, favorite=True, search=True)
            clock = [0.0]
            run = self.prepare(Path(temporary), [moving, moving, favorite, ready], clock=clock, background_delay=75)
            with patch("android_ui_smoke.time.sleep"), patch("android_ui_smoke.time.monotonic", side_effect=lambda: clock[0]), \
                    self.assertRaisesRegex(StopIteration, "before the rotation stage"):
                run.verify_library_preservation()
            restores = run.reach_content.call_args_list[1:]
            self.assertEqual(2, len(restores))
            first, second = (call.kwargs["budget"] for call in restores)
            self.assertIsNot(first, second)
            self.assertEqual((8, 8, 2, 1), (first.max_gestures, second.max_gestures, first.used, second.used))
            self.assertEqual((90, 185), (first.deadline, second.deadline))
            self.assertTrue(all(call.kwargs["direction"] == "down" for call in restores))
            self.assertEqual(3, len(self.swipes(run)))
            self.assertTrue(all(call.args[-1] == "2000" for call in self.swipes(run)))
            self.assertIn("library-filter-across-tabs", self.checks(run))
            self.assertIn("library-background-preserved", self.checks(run))
            self.assertIn("library-background-return", self.checks(run))
            for number, used in ((1, 2), (2, 1)):
                evidence = json.loads((Path(temporary) / f"scroll-search-{number:04d}.json").read_text())
                self.assertTrue(evidence["passed"])
                self.assertEqual(used, evidence["gestures_used"])
                self.assertTrue(all(sample["rotation"] == "0" for sample in evidence["samples"]))
            run.scroll.assert_not_called()

    def test_tab_restoration_rejects_visible_but_unselected_favorite(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = self.prepare(Path(temporary), [self.library(offset=100, favorite=False)])
            with patch("android_ui_smoke.time.sleep"), \
                    self.assertRaisesRegex(RuntimeError, "selection was not preserved after changing tabs"):
                run.verify_library_preservation()
            self.assertNotIn("library-filter-across-tabs", self.checks(run))
            self.assertFalse(any("KEYCODE_HOME" in call.args for call in run.adb.call_args_list))
            self.assertEqual(1, len(self.swipes(run)))
            run.scroll.assert_not_called()

    def test_background_restoration_requires_visible_search_selected_filter_and_selected_page(self):
        for invalid in ("filter", "page", "search", "offscreen-search", "offscreen-filter"):
            with self.subTest(invalid=invalid), tempfile.TemporaryDirectory() as temporary:
                favorite = self.library(offset=200, favorite=True)
                current = self.library(offset=200, favorite=invalid != "filter", search=invalid != "search")
                if invalid == "page":
                    library_tab, home_tab = (tab_target(current, label, PACKAGE) for label in ("字体库", "首页"))
                    library_tab.set("selected", "false")
                    library_tab.set("clickable", "true")
                    home_tab.set("selected", "true")
                    home_tab.set("clickable", "false")
                elif invalid == "offscreen-search":
                    next(node for node in current.iter("node") if node.get("text") == "搜索你的字体").set(
                        "bounds", "[179,10][413,40]")
                elif invalid == "offscreen-filter":
                    label_target(current, "收藏", PACKAGE).set("bounds", "[205,10][397,40]")
                run = self.prepare(Path(temporary), [favorite] + [current] * 8)
                with patch("android_ui_smoke.time.sleep"), \
                        self.assertRaisesRegex(RuntimeError, "stalled or reached a boundary"):
                    run.verify_library_preservation()
                self.assertIn("library-filter-across-tabs", self.checks(run))
                self.assertIn("library-background-preserved", self.checks(run))
                self.assertNotIn("library-background-return", self.checks(run))
                evidence = json.loads((Path(temporary) / "scroll-search-0002.json").read_text())
                self.assertFalse(evidence["passed"])
                self.assertEqual(1, evidence["gestures_used"])
                run.scroll.assert_not_called()

    def test_modal_after_either_restore_gesture_preserves_failure_and_does_not_dismiss_it(self):
        for stage in ("tab", "background"):
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as temporary:
                modal = self.fixture("family-modal")
                snapshots = [modal] if stage == "tab" else [self.library(offset=200, favorite=True), modal]
                run = self.prepare(Path(temporary), snapshots)
                with patch("android_ui_smoke.time.sleep"), \
                        self.assertRaisesRegex(RuntimeError, "No visible vertical App scroll container"):
                    run.verify_library_preservation()
                self.assertNotIn("library-background-return", self.checks(run))
                if stage == "tab":
                    self.assertNotIn("library-filter-across-tabs", self.checks(run))
                number = 1 if stage == "tab" else 2
                evidence = json.loads((Path(temporary) / f"scroll-search-{number:04d}.json").read_text())
                self.assertFalse(evidence["passed"])
                self.assertEqual(1, evidence["gestures_used"])
                self.assertEqual(ET.tostring(modal), ET.tostring(
                    ET.parse(Path(temporary) / f"scroll-search-{number:04d}-001.xml").getroot()))
                self.assertEqual(number, len(self.swipes(run)))
                self.assertFalse(any(call.args[:3] == ("shell", "input", "tap")
                                     or "user_rotation" in call.args for call in run.adb.call_args_list))
                run.scroll.assert_not_called()

    def test_original_main_content_stalling_cannot_pass_tab_restoration(self):
        with tempfile.TemporaryDirectory() as temporary:
            original = self.fixture("library-return")
            run = self.prepare(Path(temporary), [original] * 8)
            with patch("android_ui_smoke.time.sleep"), \
                    self.assertRaisesRegex(RuntimeError, "stalled or reached a boundary"):
                run.verify_library_preservation()
            self.assertNotIn("library-filter-across-tabs", self.checks(run))
            self.assertEqual(1, len(self.swipes(run)))
            evidence = json.loads((Path(temporary) / "scroll-search-0001.json").read_text())
            self.assertFalse(evidence["passed"])
            self.assertEqual(1, evidence["gestures_used"])


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

    def test_original_api28_resize_ignores_offscreen_rectangles_but_requires_real_dock(self):
        fixture = Path(__file__).parent / "ui_smoke_fixtures/api28-resize-hidden-nodes-942255ab.xml"
        before = ET.parse(fixture).getroot()
        app_nodes = [node for node in before.iter("node") if node.get("package") == PACKAGE]
        self.assertEqual(45, len(app_nodes))
        self.assertEqual(15, sum(node.get("bounds") == "[0,0][0,0]" for node in app_nodes))
        self.assertEqual((0, 0, 1080, 1920), app_window_bounds(before, PACKAGE))
        with self.assertRaises(ValueError):
            tab_target(before, "首页", PACKAGE)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            run = SmokeRun(Path("app.apk"), output, PACKAGE, None)
            run.hierarchy = Mock(return_value=before)
            run.adb = Mock()
            ready = self.hierarchy(dock=True)
            def wait(predicate, description, timeout):
                with self.assertRaises(ValueError):
                    predicate(before)
                self.assertTrue(predicate(ready))
                self.assertLessEqual(timeout, 30)
                return ready
            run.wait_ui = Mock(side_effect=wait)
            self.assertIs(ready, run.ensure_dock())
            run.adb.assert_called_once_with("shell", "input", "swipe", "540", "768", "540", "883", "2000")
            evidence = json.loads((output / "quick-return-0001.json").read_text())
            self.assertTrue(evidence["passed"])
            self.assertTrue(evidence["after_snapshot_received"])
            self.assertEqual({"首页", "字体库", "组合", "设置"}, set(evidence["navigation"]))
            self.assertEqual(ET.tostring(before), ET.tostring(ET.parse(output / evidence["before_xml"]).getroot()))

    def test_all_invisible_app_rectangles_refuse_gesture_and_preserve_failure(self):
        fixture = Path(__file__).parent / "ui_smoke_fixtures/api28-resize-hidden-nodes-942255ab.xml"
        invisible = ET.parse(fixture).getroot()
        for node in invisible.iter("node"):
            node.set("bounds", "[0,0][0,0]")
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            run = SmokeRun(Path("app.apk"), output, PACKAGE, None)
            run.hierarchy = Mock(return_value=invisible)
            run.adb = Mock()
            run.wait_ui = Mock()
            with self.assertRaisesRegex(RuntimeError, "Cannot read actual App bounds"):
                run.ensure_dock()
            run.adb.assert_not_called()
            run.wait_ui.assert_not_called()
            evidence = json.loads((output / "quick-return-0001.json").read_text())
            self.assertFalse(evidence["passed"])
            self.assertNotIn("gesture", evidence)
            self.assertFalse(evidence["after_snapshot_received"])
            self.assertEqual(ET.tostring(invisible), ET.tostring(ET.parse(output / evidence["after_xml"]).getroot()))

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


class AdbCommandEvidenceTest(unittest.TestCase):
    """Real host pipe processes exercise collection; none is an Android device."""

    def run_with_program(self, output, program):
        run = SmokeRun(Path("app.apk"), output, PACKAGE, None)
        run.adb_command = [sys.executable, "-u", "-c", program]
        return run

    def command_evidence(self, output, index=0):
        records = [json.loads(line) for line in (output / "adb-commands.jsonl").read_text().splitlines()]
        record = records[index]
        streams = []
        for stream in ("stdout", "stderr"):
            data = (output / record[stream]).read_bytes()
            self.assertEqual(len(data), record[stream + "_bytes"])
            self.assertEqual(hashlib.sha256(data).hexdigest(), record[stream + "_sha256"])
            streams.append(data)
        self.assertGreaterEqual(record["ended_monotonic_seconds"], record["started_monotonic_seconds"])
        self.assertAlmostEqual(record["elapsed_seconds"], record["ended_monotonic_seconds"] - record["started_monotonic_seconds"])
        self.assertGreaterEqual(record["raw_streams_written_monotonic_seconds"], record["ended_monotonic_seconds"])
        return records, record, streams

    def test_full_large_stdout_and_stderr_keep_logcat_scope_and_default_budget(self):
        stdout = b"stdout begin\n" + b"s" * (3 * 1024 * 1024) + b"\nstdout end\n"
        stderr = b"stderr begin\n" + b"e" * (2 * 1024 * 1024) + b"\nstderr end\n"
        program = "import sys;sys.stdout.buffer.write(b'stdout begin\\n'+b's'*(3*1024*1024)+b'\\nstdout end\\n');sys.stderr.buffer.write(b'stderr begin\\n'+b'e'*(2*1024*1024)+b'\\nstderr end\\n')"
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary);run = self.run_with_program(output, program)
            self.assertEqual(stdout.decode(), run.logcat())
            records, record, streams = self.command_evidence(output)
            self.assertEqual([stdout, stderr], streams)
            self.assertEqual(stdout, (output / "logcat.txt").read_bytes())
            self.assertEqual(["logcat", "-b", "main", "-b", "system", "-b", "crash", "-d", "-v", "threadtime"], record["arguments"][4:])
            self.assertEqual(20, record["timeout_seconds"])
            self.assertEqual(("returned", 0, True), (record["outcome"], record["returncode"], record["check"]))
            self.assertEqual(1, len(records))
            self.assertFalse(run.adb_diagnostic_errors)

    def test_fragmented_binary_streams_are_preserved_without_decoding(self):
        program = "import os,time\nfor out,err in [(b'\\x00\\xffA\\r',b'E\\x80'),(b'\\nB',b'\\x00\\n'),(b'C\\xfe',b'END')]:\n os.write(1,out);os.write(2,err);time.sleep(.01)"
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary);run = self.run_with_program(output, program)
            result = run.adb("host-pipe-fixture")
            _, record, streams = self.command_evidence(output)
            self.assertEqual([b"\x00\xffA\r\nBC\xfe", b"E\x80\x00\nEND"], streams)
            self.assertEqual([result.stdout, result.stderr], streams)
            self.assertEqual(0, record["returncode"])

    def test_nonzero_full_error_streams_survive_checked_and_unchecked_calls(self):
        prefix = f"ActivityManager: ANR in {PACKAGE}\n".encode()
        program = f"import sys;sys.stdout.buffer.write({prefix!r}+b'o'*(1024*1024));sys.stderr.buffer.write(b'error begin\\x00\\xff'+b'e'*(1024*1024)+b'error end');sys.exit(7)"
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary);run = self.run_with_program(output, program)
            with self.assertRaisesRegex(RuntimeError, r"failed \(7\)"):
                run.adb("logcat", "-d")
            result = run.adb("logcat", "-d", check=False)
            records, first, streams = self.command_evidence(output)
            self.assertEqual([prefix + b"o" * (1024 * 1024), b"error begin\x00\xff" + b"e" * (1024 * 1024) + b"error end"], streams)
            self.assertEqual("App ANR recorded by ActivityManager", crash_reason(streams[0].decode(), PACKAGE))
            _, second, unchecked_streams = self.command_evidence(output, 1)
            self.assertEqual(streams, unchecked_streams)
            self.assertEqual(7, result.returncode)
            self.assertEqual([1, 2], [record["index"] for record in records])
            self.assertTrue(first["check"]);self.assertFalse(second["check"])
            self.assertTrue(all(record["outcome"] == "returned" and record["returncode"] == 7 for record in records))

    def test_timeout_partial_bytes_survive_and_check_false_still_fails(self):
        marker = f"ActivityManager: ANR in {PACKAGE}\n".encode()
        program = f"import os,sys,time;sys.stdout.buffer.write(b'begin\\x00\\xff'+b'o'*(1024*1024)+{marker!r});sys.stdout.buffer.flush();sys.stderr.buffer.write(b'error begin'+b'e'*(1024*1024)+b'\\x00\\xfeend');sys.stderr.buffer.flush();time.sleep(3)"
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary);run = self.run_with_program(output, program)
            with self.assertRaisesRegex(RuntimeError, "adb timed out after 0.75s") as failure:
                run.adb("logcat", "-b", "main", "-b", "system", "-b", "crash", "-d", timeout=.75, check=False)
            _, record, streams = self.command_evidence(output)
            self.assertIsInstance(failure.exception.__cause__, subprocess.TimeoutExpired)
            self.assertEqual([failure.exception.__cause__.output, failure.exception.__cause__.stderr], streams)
            self.assertEqual([b"begin\x00\xff" + b"o" * (1024 * 1024) + marker, b"error begin" + b"e" * (1024 * 1024) + b"\x00\xfeend"], streams)
            self.assertEqual("App ANR recorded by ActivityManager", crash_reason(streams[0].decode(errors="replace"), PACKAGE))
            self.assertEqual("timed-out", record["outcome"])
            self.assertIsNone(record["returncode"])
            self.assertTrue(record["partial_streams"])
            self.assertEqual(.75, record["timeout_seconds"])
            self.assertFalse(record["check"])
            self.assertEqual(1, run.adb_command_count)

    def test_full_large_logcat_anr_at_start_middle_and_end_always_fails(self):
        marker = f"\nActivityManager: ANR in {PACKAGE}\n".encode()
        for before, after in [(0, 3 * 1024 * 1024), (1536 * 1024, 1536 * 1024), (3 * 1024 * 1024, 0)]:
            with self.subTest(before=before), tempfile.TemporaryDirectory() as temporary:
                program = f"import sys;sys.stdout.buffer.write(b'p'*{before}+{marker!r}+b'q'*{after});sys.stderr.buffer.write(b'system stderr'+b'e'*(1024*1024))"
                output = Path(temporary);run = self.run_with_program(output, program)
                with self.assertRaisesRegex(RuntimeError, "App ANR recorded by ActivityManager"):
                    run.assert_running()
                records, _, streams = self.command_evidence(output)
                self.assertEqual(b"p" * before + marker + b"q" * after, streams[0])
                self.assertEqual(b"system stderr" + b"e" * (1024 * 1024), streams[1])
                self.assertEqual(1, len(records))  # No later pidof can mask the crash gate.

    def test_spawn_error_records_unavailable_returncode_and_preserves_exception(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary);run = SmokeRun(Path("app.apk"), output, PACKAGE, None)
            run.adb_command = [str(output / "missing-owned-host-fixture")]
            with self.assertRaises(FileNotFoundError):
                run.adb("logcat", "-d")
            _, record, streams = self.command_evidence(output)
            self.assertEqual([b"", b""], streams)
            self.assertEqual("exception", record["outcome"])
            self.assertIsNone(record["returncode"])
            self.assertIn("FileNotFoundError", record["error"])

    def test_evidence_failure_preserves_timeout_and_cannot_make_main_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary);run = self.run_with_program(output, "import time;print('partial',flush=True);time.sleep(3)")
            with patch.object(run, "_record_adb", side_effect=OSError("evidence disk failure")):
                with self.assertRaisesRegex(RuntimeError, "adb timed out after 0.1s"):
                    run.adb("host-pipe-fixture", timeout=.1)
            self.assertIn("evidence disk failure", run.adb_diagnostic_errors[0])
            apk = output / "app.apk";apk.write_bytes(b"host path fixture")
            run = self.run_with_program(output, "print('actual child completed')")
            run.run = lambda: run.adb("host-pipe-fixture")
            run.diagnostics = Mock();run.close_snapshot_session = Mock()
            arguments = ["android_ui_smoke.py", "--apk", str(apk), "--output", str(output)]
            with patch.object(run, "_record_adb", side_effect=OSError("evidence disk failure")), \
                    patch("android_ui_smoke.sys.argv", arguments), patch("android_ui_smoke.SmokeRun", return_value=run):
                self.assertEqual(1, main())
            summary = json.loads((output / "summary.json").read_text())
            self.assertFalse(summary["passed"])
            self.assertIn("evidence disk failure", summary["error"])
            self.assertEqual(1, summary["adb_command_count"])


if __name__ == "__main__":
    unittest.main()
