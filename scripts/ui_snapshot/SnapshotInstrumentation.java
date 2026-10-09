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
import java.util.ArrayDeque;
import java.util.Arrays;
import java.util.HashMap;
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
    private String childPrefetchMode = "zero";
    private final Bundle lifecycleDiagnostics = new Bundle();
    private int nodeCount;
    private int childQueryCount;
    private long childQueryMillis;
    private long childQueryMaxMillis;
    private long childRootDeadline;
    private int rootQueryCount;
    private long rootQueryMillis;
    private long rootQueryMaxMillis;
    private int rootQueryNullCount;
    private int rootQueryNonnullCount;
    private int rootQueryTrueCount;
    private int rootQueryFalseCount;
    private int rootQueryThrownCount;
    private int rootQueryDiagnosticFailures;
    private long rootQueryStartedUptime;
    private String rootQueryKind;
    private boolean rootQueryPending;
    private final ArrayDeque<JSONObject> rootQueryRecords = new ArrayDeque<>();
    private int childQueryNullCount;
    private int childQueryNonnullCount;
    private int childQueryThrownCount;
    private int childQueryDiagnosticFailures;
    private final ArrayDeque<JSONObject> childQueryRecords = new ArrayDeque<>();
    private AccessibilityNodeInfo observedRoot;
    private final HashMap<Integer, AccessibilityNodeInfo> observedChildren = new HashMap<>();
    private int observedChildReuseCount;
    private static final int PROTOCOL = 1;
    private static final int ROOT_WAIT_MS = 8000;
    private static final int ROOT_QUERY_RECORD_LIMIT = 32;
    private static final int CHILD_QUERY_RECORD_LIMIT = 32;
    private static final int OBSERVED_CHILD_LIMIT = 32;

    @Override
    public void onCreate(Bundle arguments) {
        diagnosticTime(lifecycleDiagnostics, "helper_on_create_started_uptime_ms");
        if (Build.VERSION.SDK_INT >= 24) {
            lifecycleDiagnostics.putString("helper_process_started_uptime_ms",
                    Long.toString(android.os.Process.getStartUptimeMillis()));
        } else {
            lifecycleDiagnostics.putString("helper_process_start_time_status", "unavailable-before-api24");
        }
        super.onCreate(arguments);
        this.arguments = arguments;
        start();
    }

    @Override
    public void onStart() {
        long started = SystemClock.uptimeMillis();
        Bundle result;
        Bundle diagnostics = new Bundle();
        diagnostics.putAll(lifecycleDiagnostics);
        diagnostics.putString("helper_on_start_started_uptime_ms", Long.toString(started));
        try {
            String nonce = arguments.getString("session_nonce");
            if (nonce == null) {
                result = snapshot(connectAutomation(null), arguments.getString("filename", "hierarchy-0000.xml"),
                        getContext().getFilesDir(), null);
            } else {
                result = runSession(nonce, diagnostics);
            }
        } catch (Exception failure) {
            result = new Bundle();
            result.putString("snapshot", "failed");
            result.putString("error", failure.getClass().getSimpleName() + ": " + failure.getMessage());
        }
        result.putAll(diagnostics);
        // Instrumentation.finish tears down this one public test connection.
        finish("failed".equals(result.getString("snapshot")) ? Activity.RESULT_CANCELED : Activity.RESULT_OK, result);
    }

    private UiAutomation connectAutomation(Bundle diagnostics) throws Exception {
        diagnosticTime(diagnostics, "helper_automation_connect_started_uptime_ms");
        UiAutomation automation = getUiAutomation(UiAutomation.FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES);
        if (automation == null) throw new IllegalStateException("UiAutomation test connection failed");
        diagnosticTime(diagnostics, "helper_automation_connected_uptime_ms");
        AccessibilityServiceInfo service = automation.getServiceInfo();
        if (diagnostics != null) {
            diagnostics.putString("helper_automation_service_info_before", serviceInfoEvidence(service).toString());
        }
        service.flags |= AccessibilityServiceInfo.FLAG_INCLUDE_NOT_IMPORTANT_VIEWS
                | AccessibilityServiceInfo.FLAG_REPORT_VIEW_IDS
                | AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS;
        if (diagnostics != null) {
            diagnostics.putString("helper_automation_service_info_requested", serviceInfoEvidence(service).toString());
        }
        automation.setServiceInfo(service);
        diagnosticTime(diagnostics, "helper_automation_configured_uptime_ms");
        if (diagnostics != null) {
            // Diagnose the server's actual configuration separately from the
            // requested flags. This is one measured read, not a reconnect,
            // changed service scope or evidence that a window is available.
            diagnosticTime(diagnostics, "helper_automation_service_confirm_started_uptime_ms");
            AccessibilityServiceInfo confirmed = automation.getServiceInfo();
            diagnostics.putString("helper_automation_service_info_confirmed",
                    confirmed == null ? "null" : serviceInfoEvidence(confirmed).toString());
            diagnosticTime(diagnostics, "helper_automation_service_confirm_finished_uptime_ms");
        }
        return automation;
    }

    private static void diagnosticTime(Bundle diagnostics, String key) {
        if (diagnostics != null) diagnostics.putString(key, Long.toString(SystemClock.uptimeMillis()));
    }

    private static void lastDiagnostic(Bundle diagnostics, String suffix, String value) {
        if (diagnostics != null && value != null) {
            // Only bounded diagnostic strings enter the final session Bundle.
            diagnostics.putString("helper_last_" + suffix, value.length() > 1024 ? value.substring(0, 1024) : value);
        }
    }

    private static void lastDiagnosticTime(Bundle diagnostics, String suffix) {
        if (diagnostics != null) lastDiagnostic(diagnostics, suffix + "_uptime_ms", Long.toString(SystemClock.uptimeMillis()));
    }

    private static void acceptRequestDiagnostics(Bundle diagnostics, String requestId, String filename) {
        // Never combine the next accepted request with the previous one's times.
        for (String key : new HashSet<String>(diagnostics.keySet())) {
            if (key.startsWith("helper_last_")) diagnostics.remove(key);
        }
        lastDiagnostic(diagnostics, "request_id", requestId);
        lastDiagnostic(diagnostics, "request_filename", filename);
        lastDiagnostic(diagnostics, "request_status", "accepted");
        lastDiagnosticTime(diagnostics, "request_accepted");
    }

    private void rootQueryStarted(Bundle diagnostics, String kind) {
        if (diagnostics != null) diagnostics.remove("helper_last_root_query_returned_uptime_ms");
        lastDiagnostic(diagnostics, "request_status", "root-query");
        lastDiagnostic(diagnostics, "root_query_kind", kind);
        lastDiagnostic(diagnostics, "root_query_status", "started");
        rootQueryStartedUptime = SystemClock.uptimeMillis();
        rootQueryKind = kind;
        rootQueryPending = true;
        rootQueryCount++;
        lastDiagnostic(diagnostics, "root_query_started_uptime_ms", Long.toString(rootQueryStartedUptime));
    }

    private void rootQueryReturned(Bundle diagnostics, String outcome) {
        long finished = SystemClock.uptimeMillis();
        lastDiagnostic(diagnostics, "root_query_returned_uptime_ms", Long.toString(finished));
        lastDiagnostic(diagnostics, "root_query_status", "returned");
        recordRootQuery(finished, outcome, null);
    }

    private void recordRootQuery(long finished, String outcome, Throwable failure) {
        if (!rootQueryPending) return;
        rootQueryPending = false;
        long duration = finished - rootQueryStartedUptime;
        rootQueryMillis += duration;
        rootQueryMaxMillis = Math.max(rootQueryMaxMillis, duration);
        if ("null".equals(outcome)) rootQueryNullCount++;
        else if ("nonnull".equals(outcome)) rootQueryNonnullCount++;
        else if ("true".equals(outcome)) rootQueryTrueCount++;
        else if ("false".equals(outcome)) rootQueryFalseCount++;
        else if ("threw".equals(outcome)) rootQueryThrownCount++;
        try {
            // Record only existing query times and returns; no node metadata,
            // accessibility queries, refreshes or actions are added here.
            JSONObject record = new JSONObject().put("sequence", rootQueryCount).put("kind", rootQueryKind)
                    .put("started_uptime_ms", rootQueryStartedUptime).put("finished_uptime_ms", finished)
                    .put("duration_ms", duration).put("root_deadline_uptime_ms", childRootDeadline)
                    .put("finished_at_or_after_root_deadline", childRootDeadline != 0 && finished >= childRootDeadline)
                    .put("outcome", outcome);
            if (failure != null) record.put("exception", childDiagnosticText(failure.getClass().getName()));
            if (rootQueryRecords.size() == ROOT_QUERY_RECORD_LIMIT) rootQueryRecords.removeFirst();
            rootQueryRecords.addLast(record);
        } catch (Throwable diagnosticFailure) {
            rootQueryDiagnosticFailures++;
        }
    }

    private static int windowCountWhitespaceEnd(String value, int offset) {
        while (offset < value.length()) {
            char character = value.charAt(offset);
            if (character != ' ' && character != '\t' && character != '\r' && character != '\n') break;
            offset++;
        }
        return offset;
    }

    private static boolean completeWindowCountEvidence(String records) {
        if (records == null || records.length() > 70000) return false;
        int offset = windowCountWhitespaceEnd(records, 0);
        if (offset == records.length() || records.charAt(offset++) != '[') return false;
        offset = windowCountWhitespaceEnd(records, offset);
        if (offset < records.length() && records.charAt(offset) == ']') {
            return windowCountWhitespaceEnd(records, offset + 1) == records.length();
        }
        // This is the helper's four-number metadata grammar, not arbitrary JSON.
        // Iterate flat records rather than a recursive array regex or a lenient
        // parser that could retain comments, text, duplicate keys or hierarchy.
        java.util.regex.Matcher object = java.util.regex.Pattern.compile(
                "[ \\t\\r\\n]*\\{([^{}]*)\\}[ \\t\\r\\n]*").matcher(records);
        java.util.regex.Pattern memberPattern = java.util.regex.Pattern.compile(
                "[ \\t\\r\\n]*\"(elapsed_ms|windows|active|focused)\"[ \\t\\r\\n]*:[ \\t\\r\\n]*(0|[1-9][0-9]{0,18})[ \\t\\r\\n]*");
        while (offset < records.length()) {
            object.region(offset, records.length());
            if (!object.lookingAt()) return false;
            String fields = object.group(1);
            java.util.regex.Matcher member = memberPattern.matcher(fields);
            long[] values = new long[4];
            int seen = 0;
            int fieldOffset = 0;
            while (fieldOffset < fields.length()) {
                member.region(fieldOffset, fields.length());
                if (!member.lookingAt()) return false;
                String key = member.group(1);
                int index = "elapsed_ms".equals(key) ? 0 : "windows".equals(key) ? 1 : "active".equals(key) ? 2 : 3;
                if ((seen & (1 << index)) != 0) return false;
                seen |= 1 << index;
                try {
                    values[index] = Long.parseLong(member.group(2));
                } catch (NumberFormatException invalidNumber) {
                    return false;
                }
                fieldOffset = member.end();
                if (fieldOffset == fields.length()) break;
                if (fields.charAt(fieldOffset++) != ',') return false;
                // Require another member after a comma, even with whitespace.
                if (windowCountWhitespaceEnd(fields, fieldOffset) == fields.length()) return false;
            }
            if (seen != 15 || values[1] > Integer.MAX_VALUE || values[2] > values[1] || values[3] > values[1]) return false;
            // Active and focused can overlap; elapsed_ms can include a real
            // return after the unchanged root deadline. Preserve both facts.
            offset = object.end();
            if (offset == records.length()) return false;
            if (records.charAt(offset) == ']') {
                return windowCountWhitespaceEnd(records, offset + 1) == records.length();
            }
            if (records.charAt(offset++) != ',') return false;
            offset = windowCountWhitespaceEnd(records, offset);
        }
        return false;
    }

    private static void snapshotDiagnostics(Bundle diagnostics, Bundle result) {
        // Do not merge a snapshot result: its unprefixed snapshot/error keys
        // would change the final Instrumentation code for a normal session stop.
        lastDiagnostic(diagnostics, "snapshot_status", result.getString("snapshot"));
        String[] fields = {"error", "wait_ms", "attempts", "incomplete_roots", "root_source", "nodes",
                "last_root_package", "last_root_window_id", "last_root_child_count", "last_root_visible_child_count",
                "last_root_examined_child_count", "last_root_observation_partial", "last_root_observation_deadline_reached",
                "root_query_count", "root_query_ms", "root_query_max_ms", "root_query_null_count", "root_query_nonnull_count",
                "root_query_true_count", "root_query_false_count", "root_query_thrown_count", "root_query_records_omitted",
                "root_query_records_policy", "root_query_diagnostic_failures", "child_query_strategy", "child_prefetch_mode", "sdk_api",
                "child_query_count", "child_query_ms", "export_child_query_count", "export_child_query_ms",
                "child_query_max_ms", "child_query_null_count", "child_query_nonnull_count", "child_query_thrown_count",
                "child_query_records_omitted", "child_query_records_policy", "child_query_diagnostic_failures", "observed_child_reuse_count"};
        for (String key : fields) lastDiagnostic(diagnostics, "snapshot_" + key, result.getString(key));
        // Keep the bounded JSON complete; generic 1024-character truncation
        // would turn the retained call records into invalid JSON.
        for (String field : new String[] {"child_query_records", "root_query_records"}) {
            String records = result.getString(field);
            if (diagnostics != null && records != null && records.length() <= 70000) {
                diagnostics.putString("helper_last_snapshot_" + field, records);
            }
        }
        if (diagnostics != null) {
            // An unavailable/rejected observation must not retain old counts.
            diagnostics.remove("helper_last_snapshot_window_counts");
            String counts = result.getString("window_counts");
            if (completeWindowCountEvidence(counts)) {
                diagnostics.putString("helper_last_snapshot_window_counts", counts);
                lastDiagnostic(diagnostics, "snapshot_window_counts_status", "complete");
            } else {
                lastDiagnostic(diagnostics, "snapshot_window_counts_status", counts == null ? "unavailable"
                        : counts.length() > 70000 ? "oversize" : "invalid-schema");
            }
        }
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

    private Bundle runSession(String nonce, Bundle diagnostics) throws Exception {
        if (!nonce.matches("[0-9a-f]{32}")) throw new IllegalArgumentException("Invalid session nonce");
        childPrefetchMode = checkedChildPrefetchMode(arguments);
        diagnostics.putString("helper_session_nonce", nonce);
        diagnostics.putString("helper_pid", Integer.toString(android.os.Process.myPid()));
        diagnosticTime(diagnostics, "helper_run_session_started_uptime_ms");
        File directory = new File(getContext().getFilesDir(), "ui-snapshot-session-" + nonce);
        // A fresh private directory makes old ready/response/XML files unusable.
        if (!directory.mkdir()) throw new IllegalStateException("Cannot create fresh session directory");
        UiAutomation automation = connectAutomation(diagnostics);
        diagnosticTime(diagnostics, "helper_ready_write_started_uptime_ms");
        JSONObject ready = childPrefetchEvidence(envelope(nonce)).put("state", "ready").put("root_wait_ms", ROOT_WAIT_MS);
        try {
            JSONObject timing = new JSONObject();
            for (String key : diagnostics.keySet()) timing.put(key, diagnostics.getString(key));
            ready.put("helper_diagnostics", timing);
        } catch (Exception diagnosticFailure) {
            diagnostics.putString("helper_diagnostics_error", diagnosticFailure.toString());
        }
        // This can occur after the host's original deadline. The final existing
        // instrumentation result preserves it only as a diagnostic, never as a
        // substitute for a matching timely ready/request/response/XML exchange.
        publishJson(directory, "ready.json", ready, nonce, diagnostics, "helper_ready_published_uptime_ms");
        lastDiagnostic(diagnostics, "request_status", "none-accepted");
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
                acceptRequestDiagnostics(diagnostics, requestId, filename);
                Bundle result = snapshot(automation, filename, directory, diagnostics);
                snapshotDiagnostics(diagnostics, result);
                JSONObject values = new JSONObject();
                for (String key : result.keySet()) values.put(key, result.getString(key));
                int code = "ok".equals(result.getString("snapshot")) ? Activity.RESULT_OK : Activity.RESULT_CANCELED;
                lastDiagnostic(diagnostics, "response_code", Integer.toString(code));
                lastDiagnostic(diagnostics, "request_status", "response-write-started");
                lastDiagnosticTime(diagnostics, "response_write_started");
                try {
                    publishJson(directory, "response-" + requestId + ".json", childPrefetchEvidence(envelope(nonce))
                            .put("request_id", requestId).put("filename", filename).put("root_wait_ms", ROOT_WAIT_MS)
                            .put("code", code).put("result", values), nonce, diagnostics,
                            "helper_last_response_published_uptime_ms");
                } catch (Exception failure) {
                    lastDiagnostic(diagnostics, "request_status",
                            diagnostics.containsKey("helper_last_response_published_uptime_ms")
                                    ? "response-notice-failed" : "response-write-failed");
                    throw failure;
                }
                lastDiagnostic(diagnostics, "request_status", "response-published");
            }
            Thread.sleep(50);
        }
    }

    private static String checkedChildPrefetchMode(Bundle arguments) {
        String mode = arguments == null ? "zero" : arguments.getString("child_prefetch_mode", "zero");
        if (!"zero".equals(mode) && !"default".equals(mode)) {
            throw new IllegalArgumentException("Invalid child prefetch mode");
        }
        return mode;
    }

    private String childQueryStrategy() {
        if (Build.VERSION.SDK_INT < 33) return "legacy-platform-default";
        return "zero".equals(childPrefetchMode) ? "api33-zero-prefetch" : "api33-platform-default";
    }

    private JSONObject childPrefetchEvidence(JSONObject value) throws Exception {
        return value.put("child_prefetch_mode", childPrefetchMode).put("sdk_api", Build.VERSION.SDK_INT)
                .put("child_query_strategy", childQueryStrategy());
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
        }
        // These nonce-private files are read by the same running kernel and
        // discarded when this session closes. Close then rename publishes all
        // bytes atomically; crash durability is neither required nor reused.
        if (!temporary.renameTo(target)) throw new IllegalStateException("Cannot publish atomic session response");
    }

    private void publishJson(File directory, String filename, JSONObject value, String nonce,
            Bundle diagnostics, String publishedTimeKey) throws Exception {
        writeJson(directory, filename, value);
        diagnosticTime(diagnostics, publishedTimeKey);
        // The existing owned instrumentation pipe carries only a publication
        // notice. The host still reads and validates this exact private file;
        // missing/late notices cannot replace its original deadline or evidence.
        Bundle notice = new Bundle();
        notice.putString("luoshu_snapshot_published", envelope(nonce).put("basename", filename).toString());
        String noticeTimePrefix = "ready.json".equals(filename)
                ? "helper_ready_notice" : "helper_last_response_notice";
        diagnosticTime(diagnostics, noticeTimePrefix + "_started_uptime_ms");
        try {
            sendStatus(1, notice);
        } finally {
            diagnosticTime(diagnostics, noticeTimePrefix + "_finished_uptime_ms");
        }
    }

    private Bundle snapshot(UiAutomation automation, String filename, File outputDirectory, Bundle diagnostics) {
        nodeCount = 0;
        childQueryCount = 0;
        childQueryMillis = 0;
        childQueryMaxMillis = 0;
        childRootDeadline = 0;
        rootQueryCount = 0;
        rootQueryMillis = 0;
        rootQueryMaxMillis = 0;
        rootQueryNullCount = 0;
        rootQueryNonnullCount = 0;
        rootQueryTrueCount = 0;
        rootQueryFalseCount = 0;
        rootQueryThrownCount = 0;
        rootQueryDiagnosticFailures = 0;
        rootQueryPending = false;
        rootQueryRecords.clear();
        childQueryNullCount = 0;
        childQueryNonnullCount = 0;
        childQueryThrownCount = 0;
        childQueryDiagnosticFailures = 0;
        childQueryRecords.clear();
        clearObservedChildren();
        observedChildReuseCount = 0;
        lastDiagnosticTime(diagnostics, "snapshot_started");
        lastDiagnostic(diagnostics, "request_status", "snapshot-started");
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
            lastDiagnostic(diagnostics, "root_wait_started_uptime_ms", Long.toString(waitStarted));
            lastDiagnostic(diagnostics, "request_status", "cache-refresh");
            long deadline = waitStarted + ROOT_WAIT_MS;
            childRootDeadline = deadline;
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
                    rootQueryStarted(diagnostics, "retained-root.refresh");
                    boolean refreshed = incompleteRoot.refresh();
                    rootQueryReturned(diagnostics, Boolean.toString(refreshed));
                    if (refreshed) refreshSuccesses++; else refreshFailures++;
                    result.putString("root_refresh_attempts", Integer.toString(refreshAttempts));
                    result.putString("root_refresh_successes", Integer.toString(refreshSuccesses));
                    result.putString("root_refresh_failures", Integer.toString(refreshFailures));
                    result.putString("last_root_refresh_result", Boolean.toString(refreshed));
                    if (SystemClock.uptimeMillis() >= deadline) break;
                    lastDiagnostic(diagnostics, "request_status", "observe-descendants");
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
                        clearObservedChildren();
                        incompleteRoot.recycle();
                        incompleteRoot = null;
                    }
                }
                if (SystemClock.uptimeMillis() >= deadline) break;
                rootQueryStarted(diagnostics, "getRootInActiveWindow");
                root = automation.getRootInActiveWindow();
                rootQueryReturned(diagnostics, root == null ? "null" : "nonnull");
                if (root != null) {
                    rootSource = "getRootInActiveWindow";
                    if (SystemClock.uptimeMillis() >= deadline) break;
                    lastDiagnostic(diagnostics, "request_status", "observe-descendants");
                    if (observeRoot(result, rootObservations, root, rootSource, waitStarted) > 0) break;
                    incompleteRoots++;
                    if (incompleteRoot == null) incompleteRoot = root; else root.recycle();
                    root = null;
                }
                if (SystemClock.uptimeMillis() >= deadline) break;
                rootQueryStarted(diagnostics, "getWindows");
                List<AccessibilityWindowInfo> windows = automation.getWindows();
                rootQueryReturned(diagnostics, windows == null ? "null" : "nonnull");
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
                            rootQueryStarted(diagnostics, "window.getRoot");
                            root = window.getRoot();
                            rootQueryReturned(diagnostics, root == null ? "null" : "nonnull");
                            if (root != null) {
                                rootSource = (priority == 0 ? "active-window:" : "focused-window:") + window.getId();
                                if (SystemClock.uptimeMillis() >= deadline) break;
                                lastDiagnostic(diagnostics, "request_status", "observe-descendants");
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
            lastDiagnosticTime(diagnostics, "root_wait_finished");
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
            lastDiagnosticTime(diagnostics, "root_ready");
            lastDiagnostic(diagnostics, "request_status", "display-metadata");
            WindowManager manager = (WindowManager) getContext().getSystemService(Context.WINDOW_SERVICE);
            Display display = manager.getDefaultDisplay();
            Point size = new Point();
            display.getRealSize(size);
            File file = new File(outputDirectory, filename);
            lastDiagnosticTime(diagnostics, "export_started");
            lastDiagnostic(diagnostics, "request_status", "export-started");
            int exportChildQueries = childQueryCount;
            long exportChildQueryMillis = childQueryMillis;
            try (FileOutputStream output = new FileOutputStream(file);
                 OutputStreamWriter writer = new OutputStreamWriter(output, StandardCharsets.UTF_8)) {
                lastDiagnosticTime(diagnostics, "export_serialization_started");
                XmlSerializer xml = Xml.newSerializer();
                xml.setOutput(writer);
                xml.startDocument("UTF-8", true);
                xml.startTag(null, "hierarchy");
                xml.attribute(null, "rotation", Integer.toString(display.getRotation()));
                dumpNode(xml, root, 0, size, 0);
                xml.endTag(null, "hierarchy");
                xml.endDocument();
                lastDiagnosticTime(diagnostics, "export_serialization_finished");
                lastDiagnosticTime(diagnostics, "export_flush_started");
                writer.flush();
                lastDiagnosticTime(diagnostics, "export_flush_finished");
                // The matching response is published only after this writer
                // closes. This ephemeral XML needs no physical-disk barrier.
                lastDiagnosticTime(diagnostics, "export_close_started");
            }
            lastDiagnosticTime(diagnostics, "export_close_finished");
            result.putString("export_child_query_count", Integer.toString(childQueryCount - exportChildQueries));
            result.putString("export_child_query_ms", Long.toString(childQueryMillis - exportChildQueryMillis));
            lastDiagnosticTime(diagnostics, "export_finished");
            if (nodeCount == 0) throw new IllegalStateException("No visible accessibility nodes");
            result.putString("snapshot", "ok");
            result.putString("filename", filename);
            result.putString("nodes", Integer.toString(nodeCount));
            result.putString("root_package", text(root.getPackageName()));
        } catch (Exception failure) {
            if (rootQueryPending) recordRootQuery(SystemClock.uptimeMillis(), "threw", failure);
            if (diagnostics != null && waitStarted != 0 &&
                    !diagnostics.containsKey("helper_last_root_wait_finished_uptime_ms")) {
                lastDiagnosticTime(diagnostics, "root_wait_finished");
            }
            if (diagnostics != null && "started".equals(diagnostics.getString("helper_last_root_query_status"))) {
                lastDiagnostic(diagnostics, "root_query_status", "threw");
            }
            lastDiagnostic(diagnostics, "request_status", "snapshot-failed");
            if (waitStarted != 0) result.putString("wait_ms", Long.toString(SystemClock.uptimeMillis() - waitStarted));
            result.putString("attempts", Integer.toString(attempts));
            result.putString("incomplete_roots", Integer.toString(incompleteRoots));
            result.putString("root_source", rootSource);
            result.putString("snapshot", "failed");
            result.putString("error", failure.getClass().getSimpleName() + ": " + failure.getMessage());
        } finally {
            result.putString("root_query_count", Integer.toString(rootQueryCount));
            result.putString("root_query_ms", Long.toString(rootQueryMillis));
            result.putString("root_query_max_ms", Long.toString(rootQueryMaxMillis));
            result.putString("root_query_null_count", Integer.toString(rootQueryNullCount));
            result.putString("root_query_nonnull_count", Integer.toString(rootQueryNonnullCount));
            result.putString("root_query_true_count", Integer.toString(rootQueryTrueCount));
            result.putString("root_query_false_count", Integer.toString(rootQueryFalseCount));
            result.putString("root_query_thrown_count", Integer.toString(rootQueryThrownCount));
            result.putString("root_query_records_omitted", Integer.toString(rootQueryCount - rootQueryRecords.size()));
            result.putString("root_query_records_policy", "last-32-calls; includes-root-refresh-and-getWindows");
            result.putString("root_query_diagnostic_failures", Integer.toString(rootQueryDiagnosticFailures));
            JSONArray rootRecords = new JSONArray();
            for (JSONObject record : rootQueryRecords) rootRecords.put(record);
            result.putString("root_query_records", rootRecords.toString());
            result.putString("child_prefetch_mode", childPrefetchMode);
            result.putString("sdk_api", Integer.toString(Build.VERSION.SDK_INT));
            result.putString("child_query_strategy", childQueryStrategy());
            result.putString("child_query_count", Integer.toString(childQueryCount));
            result.putString("child_query_ms", Long.toString(childQueryMillis));
            result.putString("child_query_max_ms", Long.toString(childQueryMaxMillis));
            result.putString("child_query_null_count", Integer.toString(childQueryNullCount));
            result.putString("child_query_nonnull_count", Integer.toString(childQueryNonnullCount));
            result.putString("child_query_thrown_count", Integer.toString(childQueryThrownCount));
            result.putString("child_query_records_omitted", Integer.toString(childQueryCount - childQueryRecords.size()));
            result.putString("child_query_records_policy", "last-32-calls; node-fields-first24-last23-if-longer-than48");
            result.putString("child_query_diagnostic_failures", Integer.toString(childQueryDiagnosticFailures));
            result.putString("observed_child_reuse_count", Integer.toString(observedChildReuseCount));
            JSONArray records = new JSONArray();
            for (JSONObject record : childQueryRecords) records.put(record);
            result.putString("child_query_records", records.toString());
            clearObservedChildren();
            if (root != null) root.recycle();
            if (incompleteRoot != null) incompleteRoot.recycle();
            lastDiagnosticTime(diagnostics, "snapshot_finished");
        }
        return result;
    }

    /** A new connection can see the window root before its live children arrive.
     * Keep polling on this same connection within the original eight-second wait;
     * never declare a root-only snapshot to be usable App content.
     */
    private int observeRoot(Bundle result, JSONArray observations, AccessibilityNodeInfo root,
            String source, long waitStarted) throws Exception {
        // Retention never crosses an observation, refresh, root or request.
        clearObservedChildren();
        observedRoot = root;
        int visibleChildren = 0;
        int totalChildren = root.getChildCount();
        int examinedChildren = 0;
        for (int index = 0; index < totalChildren; index++) {
            // A platform query cannot be interrupted, but its late return must
            // not start another query outside the original root deadline.
            if (childRootDeadline != 0 && SystemClock.uptimeMillis() >= childRootDeadline) break;
            examinedChildren++;
            AccessibilityNodeInfo child = readChild(root, index, "observe-root", 0);
            if (child == null) continue;
            boolean retained = false;
            try {
                if (child.isVisibleToUser()) {
                    visibleChildren++;
                    if (observedChildren.size() < OBSERVED_CHILD_LIMIT) {
                        observedChildren.put(index, child);
                        retained = true;
                    }
                }
            } finally {
                if (!retained) child.recycle();
            }
        }
        String rootPackage = text(root.getPackageName());
        result.putString("last_root_package", rootPackage);
        result.putString("last_root_window_id", Integer.toString(root.getWindowId()));
        result.putString("last_root_child_count", Integer.toString(root.getChildCount()));
        result.putString("last_root_visible_child_count", Integer.toString(visibleChildren));
        boolean partial = examinedChildren < totalChildren;
        boolean deadlineReached = childRootDeadline != 0 && SystemClock.uptimeMillis() >= childRootDeadline;
        result.putString("last_root_examined_child_count", Integer.toString(examinedChildren));
        result.putString("last_root_observation_partial", Boolean.toString(partial));
        result.putString("last_root_observation_deadline_reached", Boolean.toString(deadlineReached));
        observations.put(new JSONObject().put("elapsed_ms", SystemClock.uptimeMillis() - waitStarted)
                .put("source", source).put("package", rootPackage).put("window_id", root.getWindowId())
                .put("children", totalChildren).put("visible_children", visibleChildren)
                .put("examined_children", examinedChildren).put("partial", partial).put("deadline_reached", deadlineReached)
                .put("refresh_result", source.equals("retained-root:refresh")
                        ? result.getString("last_root_refresh_result") : JSONObject.NULL));
        result.putString("root_observations", observations.toString());
        return visibleChildren;
    }

    private void clearObservedChildren() {
        for (AccessibilityNodeInfo child : observedChildren.values()) child.recycle();
        observedChildren.clear();
        observedRoot = null;
    }

    private AccessibilityNodeInfo takeObservedChild(AccessibilityNodeInfo node, int index) {
        if (node != observedRoot) return null;
        AccessibilityNodeInfo child = observedChildren.remove(index);
        if (child != null) observedChildReuseCount++;
        return child;
    }

    private static String childDiagnosticText(CharSequence value) {
        if (value == null) return "";
        String text = value.toString();
        return text.length() > 48 ? text.substring(0, 24) + "…" + text.substring(text.length() - 23) : text;
    }

    private static JSONObject childNodeEvidence(AccessibilityNodeInfo node) throws Exception {
        // These fields are already on the returned node; none issues an
        // accessibility query, refresh, action or IPC.
        CharSequence className = node.getClassName();
        String resourceId = node.getViewIdResourceName();
        return new JSONObject().put("window", node.getWindowId())
                .put("class", childDiagnosticText(className)).put("id", childDiagnosticText(resourceId))
                .put("fields_truncated", className != null && className.length() > 48 || resourceId != null && resourceId.length() > 48);
    }

    private void recordChildQuery(AccessibilityNodeInfo node, int index, String stage, int depth,
            long started, long finished, AccessibilityNodeInfo child, Throwable failure) {
        try {
            JSONObject record = new JSONObject().put("sequence", childQueryCount).put("stage", stage)
                    .put("depth", depth).put("index", index).put("started_uptime_ms", started)
                    .put("finished_uptime_ms", finished).put("duration_ms", finished - started)
                    .put("root_deadline_uptime_ms", childRootDeadline)
                    .put("finished_at_or_after_root_deadline", childRootDeadline != 0 && finished >= childRootDeadline)
                    .put("outcome", failure != null ? "threw" : child == null ? "null" : "nonnull");
            if (failure != null) record.put("exception", childDiagnosticText(failure.getClass().getName()));
            try {
                record.put("parent", childNodeEvidence(node));
                if (child != null) {
                    record.put("child", childNodeEvidence(child)).put("visible", child.isVisibleToUser());
                }
            } catch (Throwable metadataFailure) {
                childQueryDiagnosticFailures++;
                record.put("metadata_status", "failed");
            }
            if (childQueryRecords.size() == CHILD_QUERY_RECORD_LIMIT) childQueryRecords.removeFirst();
            childQueryRecords.addLast(record);
        } catch (Throwable diagnosticFailure) {
            // Diagnostics never replace the real getter return or exception.
            childQueryDiagnosticFailures++;
        }
    }

    private AccessibilityNodeInfo readChild(AccessibilityNodeInfo node, int index, String stage, int depth) {
        long started = SystemClock.uptimeMillis();
        childQueryCount++;
        AccessibilityNodeInfo child = null;
        Throwable failure = null;
        try {
            // API33 exposes a public strategy overload. Zero requests this child
            // without descendant prefetch; explicit default and older APIs use
            // the platform getter. Cache and root selection remain unchanged.
            // Real Android measurements, not JVM fixtures, decide its cost.
            child = Build.VERSION.SDK_INT >= 33 && "zero".equals(childPrefetchMode) ? node.getChild(index, 0) : node.getChild(index);
            if (child == null) childQueryNullCount++; else childQueryNonnullCount++;
            return child;
        } catch (RuntimeException | Error queryFailure) {
            failure = queryFailure;
            childQueryThrownCount++;
            throw queryFailure;
        } finally {
            long finished = SystemClock.uptimeMillis();
            childQueryMillis += finished - started;
            childQueryMaxMillis = Math.max(childQueryMaxMillis, finished - started);
            recordChildQuery(node, index, stage, depth, started, finished, child, failure);
        }
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
            AccessibilityNodeInfo child = takeObservedChild(node, childIndex);
            if (child == null) child = readChild(node, childIndex, "export", depth);
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
