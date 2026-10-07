package io.github.xgl34222220.luoshu.uisnapshot;

import android.app.Activity;
import android.app.Instrumentation;
import android.app.UiAutomation;
import android.accessibilityservice.AccessibilityServiceInfo;
import android.content.Context;
import android.graphics.Point;
import android.graphics.Rect;
import android.os.Bundle;
import android.os.Build;
import android.os.SystemClock;
import android.util.Xml;
import android.view.Display;
import android.view.WindowManager;
import android.view.accessibility.AccessibilityNodeInfo;
import android.view.accessibility.AccessibilityWindowInfo;

import org.xmlpull.v1.XmlSerializer;
import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.FilenameFilter;
import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

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
    private static final int PROTOCOL = 1;
    private static final int ROOT_WAIT_MS = 8000;

    @Override
    public void onCreate(Bundle arguments) {
        super.onCreate(arguments);
        this.arguments = arguments;
        start();
    }

    @Override
    public void onStart() {
        Bundle result;
        try {
            String nonce = arguments.getString("session_nonce");
            if (nonce == null) {
                result = snapshot(connectAutomation(), arguments.getString("filename", "hierarchy-0000.xml"),
                        getContext().getFilesDir());
            } else {
                result = runSession(nonce);
            }
        } catch (Exception failure) {
            result = new Bundle();
            result.putString("snapshot", "failed");
            result.putString("error", failure.getClass().getSimpleName() + ": " + failure.getMessage());
        }
        // Instrumentation.finish tears down this one public test connection.
        finish("failed".equals(result.getString("snapshot")) ? Activity.RESULT_CANCELED : Activity.RESULT_OK, result);
    }

    private UiAutomation connectAutomation() {
        UiAutomation automation = getUiAutomation(UiAutomation.FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES);
        if (automation == null) throw new IllegalStateException("UiAutomation test connection failed");
        AccessibilityServiceInfo service = automation.getServiceInfo();
        service.flags |= AccessibilityServiceInfo.FLAG_INCLUDE_NOT_IMPORTANT_VIEWS
                | AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS
                | AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS;
        automation.setServiceInfo(service);
        return automation;
    }

    private static JSONObject serviceInfoEvidence(AccessibilityServiceInfo info) throws Exception {
        JSONObject evidence = new JSONObject().put("flags", info.flags).put("event_types", info.eventTypes)
                .put("feedback_type", info.feedbackType).put("notification_timeout", info.notificationTimeout)
                .put("capabilities", info.getCapabilities());
        if (info.packageNames == null) {
            evidence.put("package_names", JSONObject.NULL);
        } else {
            JSONArray packages = new JSONArray();
            for (String name : info.packageNames) packages.put(name);
            evidence.put("package_names", packages);
        }
        if (Build.VERSION.SDK_INT >= 29) {
            evidence.put("interactive_ui_timeout", info.getInteractiveUiTimeoutMillis())
                    .put("noninteractive_ui_timeout", info.getNonInteractiveUiTimeoutMillis());
        }
        return evidence;
    }

    private static void refreshLegacyAccessibilityCache(UiAutomation automation, Bundle result,
            long deadline) throws Exception {
        long started = SystemClock.uptimeMillis();
        result.putString("accessibility_cache_refresh_method", "public-setServiceInfo-unchanged");
        result.putString("accessibility_service_info_unchanged", "false");
        try {
            if (started >= deadline) throw new IllegalStateException("Snapshot root deadline expired before cache refresh");
            AccessibilityServiceInfo info = automation.getServiceInfo();
            if (info == null) throw new IllegalStateException("Cannot read this snapshot connection's service configuration");
            int flags = info.flags;
            int eventTypes = info.eventTypes;
            int feedbackType = info.feedbackType;
            long notificationTimeout = info.notificationTimeout;
            int capabilities = info.getCapabilities();
            String[] packageNames = info.packageNames == null ? null : info.packageNames.clone();
            int interactiveTimeout = Build.VERSION.SDK_INT >= 29 ? info.getInteractiveUiTimeoutMillis() : -1;
            int noninteractiveTimeout = Build.VERSION.SDK_INT >= 29 ? info.getNonInteractiveUiTimeoutMillis() : -1;
            result.putString("accessibility_service_info_before", serviceInfoEvidence(info).toString());
            if (SystemClock.uptimeMillis() >= deadline) {
                throw new IllegalStateException("Snapshot root deadline expired before public service refresh");
            }
            // Android 9's public setter clears the client accessibility cache
            // before forwarding the unchanged service info. This is confined to
            // this existing test connection; no flags, events or packages change.
            automation.setServiceInfo(info);
            if (SystemClock.uptimeMillis() >= deadline) {
                throw new IllegalStateException("Snapshot root deadline expired before service confirmation");
            }
            AccessibilityServiceInfo confirmed = automation.getServiceInfo();
            if (confirmed == null) throw new IllegalStateException("Cannot confirm this snapshot connection's service configuration");
            result.putString("accessibility_service_info_after", serviceInfoEvidence(confirmed).toString());
            if (flags != confirmed.flags || eventTypes != confirmed.eventTypes ||
                    feedbackType != confirmed.feedbackType || notificationTimeout != confirmed.notificationTimeout ||
                    capabilities != confirmed.getCapabilities() || !Arrays.equals(packageNames, confirmed.packageNames) ||
                    Build.VERSION.SDK_INT >= 29 && (interactiveTimeout != confirmed.getInteractiveUiTimeoutMillis() ||
                            noninteractiveTimeout != confirmed.getNonInteractiveUiTimeoutMillis())) {
                throw new IllegalStateException("Snapshot service configuration changed during public cache refresh");
            }
            if (SystemClock.uptimeMillis() >= deadline) {
                throw new IllegalStateException("Snapshot root deadline expired during public service refresh");
            }
            result.putString("accessibility_service_info_unchanged", "true");
            result.putString("accessibility_cache_cleared", "public-setServiceInfo-unchanged");
        } finally {
            result.putString("accessibility_cache_refresh_ms", Long.toString(SystemClock.uptimeMillis() - started));
        }
    }

    private Bundle runSession(String nonce) throws Exception {
        if (!nonce.matches("[0-9a-f]{32}")) throw new IllegalArgumentException("Invalid session nonce");
        File directory = new File(getContext().getFilesDir(), "ui-snapshot-session-" + nonce);
        // A fresh private directory makes old ready/response/XML files unusable.
        if (!directory.mkdir()) throw new IllegalStateException("Cannot create fresh session directory");
        UiAutomation automation = connectAutomation();
        writeJson(directory, "ready.json", envelope(nonce).put("state", "ready").put("root_wait_ms", ROOT_WAIT_MS));
        Set<String> requests = new HashSet<>();
        Set<String> filenames = new HashSet<>();
        while (true) {
            File stop = new File(directory, "stop.json");
            if (stop.exists()) {
                validateEnvelope(readJson(stop), nonce);
                writeJson(directory, "closed.json", envelope(nonce).put("state", "closed"));
                Bundle result = new Bundle();
                result.putString("session", "finished");
                result.putString("session_nonce", nonce);
                return result;
            }
            // The independent helper is compiled directly against android.jar
            // without the App's desugaring pass; avoid LambdaMetafactory here.
            File[] pending = directory.listFiles(new FilenameFilter() {
                @Override
                public boolean accept(File parent, String name) {
                    return name.matches("request-[0-9a-f]{32}\\.json");
                }
            });
            if (pending == null) throw new IllegalStateException("Session request directory unavailable");
            Arrays.sort(pending);
            for (File file : pending) {
                String requestId = file.getName().substring(8, 40);
                if (requests.contains(requestId)) continue;
                JSONObject request = readJson(file);
                validateEnvelope(request, nonce);
                if (!(request.get("request_id") instanceof String) || !requestId.equals(request.getString("request_id"))) {
                    throw new IllegalArgumentException("Request ID does not match its private filename");
                }
                Object budget = request.get("root_wait_ms");
                if (!(budget instanceof Integer) || ((Integer) budget) != ROOT_WAIT_MS) {
                    throw new IllegalArgumentException("Snapshot root wait must remain 8000ms");
                }
                if (!(request.get("filename") instanceof String)) {
                    throw new IllegalArgumentException("Snapshot filename must be a string");
                }
                String filename = request.getString("filename");
                if (!filename.matches("hierarchy-[0-9]{4,8}\\.xml") || !filenames.add(filename)) {
                    throw new IllegalArgumentException("Invalid or reused snapshot filename");
                }
                if (new File(directory, filename).exists()) {
                    throw new IllegalStateException("Snapshot file cannot be reused");
                }
                requests.add(requestId);
                Bundle result = snapshot(automation, filename, directory);
                JSONObject values = new JSONObject();
                for (String key : result.keySet()) values.put(key, result.getString(key));
                int code = "ok".equals(result.getString("snapshot")) ? Activity.RESULT_OK : Activity.RESULT_CANCELED;
                writeJson(directory, "response-" + requestId + ".json", envelope(nonce)
                        .put("request_id", requestId).put("filename", filename).put("root_wait_ms", ROOT_WAIT_MS)
                        .put("code", code).put("result", values));
            }
            Thread.sleep(50);
        }
    }

    private static JSONObject envelope(String nonce) throws Exception {
        return new JSONObject().put("protocol", PROTOCOL).put("nonce", nonce);
    }

    private static void validateEnvelope(JSONObject value, String nonce) throws Exception {
        Object protocol = value.get("protocol");
        if (!(protocol instanceof Integer) || ((Integer) protocol) != PROTOCOL
                || !(value.get("nonce") instanceof String)
                || !nonce.equals(value.getString("nonce"))) {
            throw new IllegalArgumentException("Session envelope mismatch");
        }
    }

    private static JSONObject readJson(File file) throws Exception {
        try (FileInputStream input = new FileInputStream(file);
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[1024];
            int count;
            while ((count = input.read(buffer)) != -1) {
                if (output.size() + count > 16384) throw new IllegalArgumentException("Session request too large");
                output.write(buffer, 0, count);
            }
            return new JSONObject(new String(output.toByteArray(), StandardCharsets.UTF_8));
        }
    }

    private static void writeJson(File directory, String filename, JSONObject value) throws Exception {
        File target = new File(directory, filename);
        File temporary = new File(directory, filename + ".tmp");
        if (target.exists() || temporary.exists()) throw new IllegalStateException("Session response cannot be reused");
        try (FileOutputStream output = new FileOutputStream(temporary)) {
            output.write(value.toString().getBytes(StandardCharsets.UTF_8));
            output.getFD().sync();
        }
        if (!temporary.renameTo(target)) throw new IllegalStateException("Cannot publish atomic session response");
    }

    private Bundle snapshot(UiAutomation automation, String filename, File outputDirectory) {
        nodeCount = 0;
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
            if (!filename.matches("hierarchy-[0-9]{4,8}\\.xml")) {
                throw new IllegalArgumentException("Invalid snapshot filename");
            }
            // On older APIs a fresh test connection can precede window tracking.
            // Keep this bounded and read only active/focused real windows; the
            // host still checks the App package, selected tab and page content.
            waitStarted = SystemClock.uptimeMillis();
            long deadline = waitStarted + ROOT_WAIT_MS;
            // A persistent test connection can retain an obsolete tab node
            // while a different subtree already reflects the new page. Clear
            // only this connection's accessibility-node cache before querying
            // live state; never infer selection from the page marker alone.
            if (Build.VERSION.SDK_INT >= 34) {
                boolean cleared = automation.clearCache();
                result.putString("accessibility_cache_cleared", Boolean.toString(cleared));
                if (!cleared) throw new IllegalStateException("Cannot clear this snapshot connection's node cache");
            } else {
                refreshLegacyAccessibilityCache(automation, result, deadline);
            }
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
            File file = new File(outputDirectory, filename);
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
        } catch (Exception failure) {
            if (waitStarted != 0) result.putString("wait_ms", Long.toString(SystemClock.uptimeMillis() - waitStarted));
            result.putString("attempts", Integer.toString(attempts));
            result.putString("incomplete_roots", Integer.toString(incompleteRoots));
            result.putString("root_source", rootSource);
            result.putString("snapshot", "failed");
            result.putString("error", failure.getClass().getSimpleName() + ": " + failure.getMessage());
        } finally {
            if (root != null) root.recycle();
            if (incompleteRoot != null) incompleteRoot.recycle();
        }
        return result;
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
