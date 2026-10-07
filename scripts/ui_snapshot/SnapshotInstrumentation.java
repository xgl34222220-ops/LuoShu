package io.github.xgl34222220.luoshu.uisnapshot;

import android.app.Activity;
import android.app.Instrumentation;
import android.app.UiAutomation;
import android.accessibilityservice.AccessibilityServiceInfo;
import android.content.Context;
import android.graphics.Point;
import android.graphics.Rect;
import android.os.Bundle;
import android.os.SystemClock;
import android.util.Xml;
import android.view.Display;
import android.view.WindowManager;
import android.view.accessibility.AccessibilityNodeInfo;
import android.view.accessibility.AccessibilityWindowInfo;

import org.xmlpull.v1.XmlSerializer;
import org.json.JSONArray;
import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.util.List;

/** Read a live AccessibilityNodeInfo tree without changing or launching App UI.
 *
 * The platform uiautomator CLI waits for one second of global accessibility
 * silence, which continuously updating production UI can prevent on old APIs.
 * This reader does not require global idle; the host still polls and verifies
 * selected tabs, content, bounds, process liveness and crashes against real UI.
 */
public final class SnapshotInstrumentation extends Instrumentation {
    private Bundle arguments;
    private int nodeCount;

    @Override
    public void onCreate(Bundle arguments) {
        super.onCreate(arguments);
        this.arguments = arguments;
        start();
    }

    @Override
    public void onStart() {
        Bundle result = new Bundle();
        AccessibilityNodeInfo root = null;
        AccessibilityNodeInfo incompleteRoot = null;
        JSONArray rootObservations = new JSONArray();
        JSONArray windowCounts = new JSONArray();
        long waitStarted = 0;
        int attempts = 0;
        int incompleteRoots = 0;
        int refreshAttempts = 0;
        int refreshSuccesses = 0;
        int refreshFailures = 0;
        String rootSource = "unavailable";
        result.putString("root_refresh_attempts", "0");
        result.putString("root_refresh_successes", "0");
        result.putString("root_refresh_failures", "0");
        result.putString("root_observations", "[]");
        result.putString("window_counts", "[]");
        try {
            String filename = arguments.getString("filename", "hierarchy-0000.xml");
            if (!filename.matches("hierarchy-[0-9]{4,8}\\.xml")) {
                throw new IllegalArgumentException("Invalid snapshot filename");
            }
            UiAutomation automation = getUiAutomation(UiAutomation.FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES);
            if (automation == null) throw new IllegalStateException("UiAutomation test connection failed");
            AccessibilityServiceInfo service = automation.getServiceInfo();
            service.flags |= AccessibilityServiceInfo.FLAG_INCLUDE_NOT_IMPORTANT_VIEWS
                    | AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS
                    | AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS;
            automation.setServiceInfo(service);
            // On older APIs a fresh test connection can precede window tracking.
            // Keep this bounded and read only active/focused real windows; the
            // host still checks the App package, selected tab and page content.
            waitStarted = SystemClock.uptimeMillis();
            long deadline = waitStarted + 8000;
            while (root == null && SystemClock.uptimeMillis() < deadline) {
                attempts++;
                // refresh() re-queries this real node's current state rather
                // than relying on the connection's cached incomplete root.
                // It shares the original connection and eight-second deadline.
                if (incompleteRoot != null) {
                    refreshAttempts++;
                    boolean refreshed = incompleteRoot.refresh();
                    if (refreshed) refreshSuccesses++; else refreshFailures++;
                    result.putString("root_refresh_attempts", Integer.toString(refreshAttempts));
                    result.putString("root_refresh_successes", Integer.toString(refreshSuccesses));
                    result.putString("root_refresh_failures", Integer.toString(refreshFailures));
                    result.putString("last_root_refresh_result", Boolean.toString(refreshed));
                    int visibleChildren = observeRoot(result, rootObservations, incompleteRoot,
                            "retained-root:refresh", waitStarted);
                    if (refreshed && visibleChildren > 0 && SystemClock.uptimeMillis() < deadline) {
                        root = incompleteRoot;
                        incompleteRoot = null;
                        rootSource = "retained-root:refresh";
                        break;
                    }
                    if (!refreshed) {
                        // The node is obsolete; never reuse it as UI evidence.
                        incompleteRoot.recycle();
                        incompleteRoot = null;
                    }
                }
                if (SystemClock.uptimeMillis() >= deadline) break;
                root = automation.getRootInActiveWindow();
                if (root != null) {
                    rootSource = "getRootInActiveWindow";
                    if (observeRoot(result, rootObservations, root, rootSource, waitStarted) > 0) break;
                    incompleteRoots++;
                    if (incompleteRoot == null) incompleteRoot = root; else root.recycle();
                    root = null;
                }
                if (SystemClock.uptimeMillis() >= deadline) break;
                List<AccessibilityWindowInfo> windows = automation.getWindows();
                try {
                    int active = 0;
                    int focused = 0;
                    for (AccessibilityWindowInfo window : windows) {
                        if (window.isActive()) active++;
                        if (window.isFocused()) focused++;
                    }
                    windowCounts.put(new JSONObject().put("elapsed_ms", SystemClock.uptimeMillis() - waitStarted)
                            .put("windows", windows.size()).put("active", active).put("focused", focused));
                    result.putString("window_counts", windowCounts.toString());
                    // Prefer active over merely focused if both are reported.
                    for (int priority = 0; priority < 2 && root == null; priority++) {
                        for (AccessibilityWindowInfo window : windows) {
                            if (SystemClock.uptimeMillis() >= deadline) break;
                            if (!(priority == 0 ? window.isActive() : window.isFocused())) continue;
                            root = window.getRoot();
                            if (root != null) {
                                rootSource = (priority == 0 ? "active-window:" : "focused-window:") + window.getId();
                                if (observeRoot(result, rootObservations, root, rootSource, waitStarted) > 0) break;
                                incompleteRoots++;
                                if (incompleteRoot == null) incompleteRoot = root; else root.recycle();
                                root = null;
                            }
                        }
                    }
                } finally {
                    for (AccessibilityWindowInfo window : windows) window.recycle();
                }
                if (root == null) {
                    long remaining = deadline - SystemClock.uptimeMillis();
                    if (remaining > 0) Thread.sleep(Math.min(100, remaining));
                }
            }
            result.putString("wait_ms", Long.toString(SystemClock.uptimeMillis() - waitStarted));
            result.putString("attempts", Integer.toString(attempts));
            result.putString("incomplete_roots", Integer.toString(incompleteRoots));
            result.putString("root_source", rootSource);
            if (root != null && SystemClock.uptimeMillis() >= deadline) {
                root.recycle();
                root = null;
            }
            if (root == null) throw new IllegalStateException(incompleteRoots == 0
                    ? "No active accessibility window"
                    : "No visible accessibility descendants within 8s");
            WindowManager manager = (WindowManager) getContext().getSystemService(Context.WINDOW_SERVICE);
            Display display = manager.getDefaultDisplay();
            Point size = new Point();
            display.getRealSize(size);
            File file = new File(getContext().getFilesDir(), filename);
            try (FileOutputStream output = new FileOutputStream(file);
                 OutputStreamWriter writer = new OutputStreamWriter(output, StandardCharsets.UTF_8)) {
                XmlSerializer xml = Xml.newSerializer();
                xml.setOutput(writer);
                xml.startDocument("UTF-8", true);
                xml.startTag(null, "hierarchy");
                xml.attribute(null, "rotation", Integer.toString(display.getRotation()));
                dumpNode(xml, root, 0, size, 0);
                xml.endTag(null, "hierarchy");
                xml.endDocument();
                writer.flush();
                output.getFD().sync();
            }
            if (nodeCount == 0) throw new IllegalStateException("No visible accessibility nodes");
            result.putString("snapshot", "ok");
            result.putString("filename", filename);
            result.putString("nodes", Integer.toString(nodeCount));
            result.putString("root_package", text(root.getPackageName()));
            finish(Activity.RESULT_OK, result);
        } catch (Exception failure) {
            if (waitStarted != 0) result.putString("wait_ms", Long.toString(SystemClock.uptimeMillis() - waitStarted));
            result.putString("attempts", Integer.toString(attempts));
            result.putString("incomplete_roots", Integer.toString(incompleteRoots));
            result.putString("root_source", rootSource);
            result.putString("snapshot", "failed");
            result.putString("error", failure.getClass().getSimpleName() + ": " + failure.getMessage());
            finish(Activity.RESULT_CANCELED, result);
        } finally {
            if (root != null) root.recycle();
            if (incompleteRoot != null) incompleteRoot.recycle();
        }
    }

    /** A new connection can see the window root before its live children arrive.
     * Keep polling on this same connection within the original eight-second wait;
     * never declare a root-only snapshot to be usable App content.
     */
    private static int observeRoot(Bundle result, JSONArray observations, AccessibilityNodeInfo root,
            String source, long waitStarted) throws Exception {
        int visibleChildren = 0;
        for (int index = 0; index < root.getChildCount(); index++) {
            AccessibilityNodeInfo child = root.getChild(index);
            if (child == null) continue;
            try {
                if (child.isVisibleToUser()) visibleChildren++;
            } finally {
                child.recycle();
            }
        }
        String rootPackage = text(root.getPackageName());
        result.putString("last_root_package", rootPackage);
        result.putString("last_root_window_id", Integer.toString(root.getWindowId()));
        result.putString("last_root_child_count", Integer.toString(root.getChildCount()));
        result.putString("last_root_visible_child_count", Integer.toString(visibleChildren));
        observations.put(new JSONObject().put("elapsed_ms", SystemClock.uptimeMillis() - waitStarted)
                .put("source", source).put("package", rootPackage).put("window_id", root.getWindowId())
                .put("children", root.getChildCount()).put("visible_children", visibleChildren)
                .put("refresh_result", source.equals("retained-root:refresh")
                        ? result.getString("last_root_refresh_result") : JSONObject.NULL));
        result.putString("root_observations", observations.toString());
        return visibleChildren;
    }

    private void dumpNode(XmlSerializer xml, AccessibilityNodeInfo node, int index, Point size, int depth) throws Exception {
        if (depth > 256 || nodeCount >= 20000) {
            throw new IllegalStateException("Accessibility tree exceeded snapshot bounds");
        }
        Rect bounds = new Rect();
        node.getBoundsInScreen(bounds);
        if (!bounds.intersect(0, 0, size.x, size.y)) bounds.setEmpty();
        xml.startTag(null, "node");
        xml.attribute(null, "index", Integer.toString(index));
        xml.attribute(null, "text", text(node.getText()));
        xml.attribute(null, "resource-id", text(node.getViewIdResourceName()));
        xml.attribute(null, "class", text(node.getClassName()));
        xml.attribute(null, "package", text(node.getPackageName()));
        xml.attribute(null, "content-desc", text(node.getContentDescription()));
        xml.attribute(null, "checkable", Boolean.toString(node.isCheckable()));
        xml.attribute(null, "checked", Boolean.toString(node.isChecked()));
        xml.attribute(null, "clickable", Boolean.toString(node.isClickable()));
        xml.attribute(null, "enabled", Boolean.toString(node.isEnabled()));
        xml.attribute(null, "focusable", Boolean.toString(node.isFocusable()));
        xml.attribute(null, "focused", Boolean.toString(node.isFocused()));
        xml.attribute(null, "scrollable", Boolean.toString(node.isScrollable()));
        xml.attribute(null, "long-clickable", Boolean.toString(node.isLongClickable()));
        xml.attribute(null, "password", Boolean.toString(node.isPassword()));
        xml.attribute(null, "selected", Boolean.toString(node.isSelected()));
        xml.attribute(null, "bounds", "[" + bounds.left + "," + bounds.top + "][" + bounds.right + "," + bounds.bottom + "]");
        nodeCount++;
        for (int childIndex = 0; childIndex < node.getChildCount(); childIndex++) {
            AccessibilityNodeInfo child = node.getChild(childIndex);
            if (child == null) continue;
            try {
                if (child.isVisibleToUser()) dumpNode(xml, child, childIndex, size, depth + 1);
            } finally {
                child.recycle();
            }
        }
        xml.endTag(null, "node");
    }

    private static String text(CharSequence value) {
        if (value == null) return "";
        String input = value.toString();
        StringBuilder clean = new StringBuilder(input.length());
        for (int offset = 0; offset < input.length();) {
            int point = input.codePointAt(offset);
            offset += Character.charCount(point);
            if (point == 9 || point == 10 || point == 13 ||
                    point >= 0x20 && point <= 0xD7FF || point >= 0xE000 && point <= 0xFFFD ||
                    point >= 0x10000 && point <= 0x10FFFF) {
                clean.appendCodePoint(point);
            }
        }
        return clean.toString();
    }
}
