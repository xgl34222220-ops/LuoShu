#!/usr/bin/env python3
"""Run production Java snapshot/file code with deterministic Android boundaries.

The JVM writes real files and independent JVM readers verify complete JSON/XML.
Node fixtures exercise rejection/export mechanics; they are not device evidence.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


class NativeSnapshotPublicationTest(unittest.TestCase):
    def test_production_java_snapshot_visibility_errors_and_bounded_diagnostics(self):
        java = shutil.which('java')
        if java is None:
            self.skipTest('Production Java regression requires the host JDK')
        source = (Path(__file__).parent / 'ui_snapshot' / 'SnapshotInstrumentation.java').read_text()
        for constant in ('ROOT_WAIT_MS = 8000', 'CHILD_QUERY_RECORD_LIMIT = 32', 'OBSERVED_CHILD_LIMIT = 32'):
            self.assertIn(f'private static final int {constant};', source)

        def method(signature):
            start = source.index(signature)
            return source[start:source.index('\n    }', start) + len('\n    }')]

        methods = '\n'.join(method(signature) for signature in (
            '    public void onCreate(',
            '    public void onStart()',
            '    private UiAutomation connectAutomation(',
            '    private static void diagnosticTime(',
            '    private static void lastDiagnostic(',
            '    private static void lastDiagnosticTime(',
            '    private static void acceptRequestDiagnostics(',
            '    private static void rootQueryStarted(',
            '    private static void rootQueryReturned(',
            '    private static void snapshotDiagnostics(',
            '    private static JSONObject envelope(',
            '    private static void writeJson(',
            '    private void publishJson(',
            '    private Bundle snapshot(',
            '    private int observeRoot(',
            '    private void clearObservedChildren(',
            '    private AccessibilityNodeInfo takeObservedChild(',
            '    private static String childDiagnosticText(',
            '    private static JSONObject childNodeEvidence(',
            '    private void recordChildQuery(',
            '    private AccessibilityNodeInfo readChild(',
            '    private void dumpNode(',
            '    private static String text(',
        ))
        harness = r'''
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.*;
import javax.xml.stream.*;
import javax.xml.parsers.DocumentBuilderFactory;
import org.w3c.dom.*;
class InstrumentationBoundary {
    void onCreate(NativeSnapshotPublicationHarness.Bundle arguments) {}
}
public class NativeSnapshotPublicationHarness extends InstrumentationBoundary {
    private Bundle arguments = new Bundle();
    private final Bundle lifecycleDiagnostics = new Bundle();
    private int nodeCount, childQueryCount;
    private long childQueryMillis, childQueryMaxMillis, childRootDeadline;
    private int childQueryNullCount, childQueryNonnullCount, childQueryThrownCount, childQueryDiagnosticFailures;
    private final ArrayDeque<JSONObject> childQueryRecords = new ArrayDeque<>();
    private AccessibilityNodeInfo observedRoot;
    private final HashMap<Integer,AccessibilityNodeInfo> observedChildren = new HashMap<>();
    private int observedChildReuseCount;
    private static final int PROTOCOL = 1;
    private static final int ROOT_WAIT_MS = 8000;
    private static final int CHILD_QUERY_RECORD_LIMIT = 32;
    // Test-only boundary override exercises the production overflow/fallback
    // path at zero: it reproduces observe/requery behavior without pretending
    // to execute all literal 6eb source, or changing the real getter boundary.
    private static int OBSERVED_CHILD_LIMIT = 32;
    private static final String NONCE = "0123456789abcdef0123456789abcdef";
    static class Bundle {
        final Map<String,String> values = new HashMap<>();
        void putString(String key,String value) { values.put(key,value); }
        String getString(String key) { return values.get(key); }
        String getString(String key,String fallback) { return values.getOrDefault(key,fallback); }
        void putAll(Bundle other) { values.putAll(other.values); }
        Set<String> keySet() { return values.keySet(); }
        void remove(String key) { values.remove(key); }
        boolean containsKey(String key) { return values.containsKey(key); }
    }
    static class SystemClock {
        static long now=100;
        static long uptimeMillis() { return now; }
    }
    static class Build {
        static class VERSION { static int SDK_INT=34; }
    }
    static class Activity { static final int RESULT_OK=-1, RESULT_CANCELED=0; }
    static class Context {
        static final String WINDOW_SERVICE="window";
        File directory;
        File getFilesDir() { return directory; }
        Object getSystemService(String name) { return new WindowManager(); }
    }
    static class Point { int x,y; }
    static class Rect {
        int left,top,right,bottom;
        boolean intersect(int l,int t,int r,int b) {
            left=Math.max(left,l); top=Math.max(top,t); right=Math.min(right,r); bottom=Math.min(bottom,b);
            return left<right && top<bottom;
        }
        void setEmpty() { left=top=right=bottom=0; }
    }
    static class WindowManager { Display getDefaultDisplay() { return new Display(); } }
    static class Display {
        void getRealSize(Point p) { p.x=100; p.y=200; }
        int getRotation() { return 1; }
    }
    static class AccessibilityNodeInfo {
        static int getterCalls, createdCopies, recycledCopies;
        static final List<AccessibilityNodeInfo> copies=new ArrayList<>();
        final String value;
        final boolean visible;
        final List<AccessibilityNodeInfo> children = new ArrayList<>();
        boolean recycled, throwChild, throwMetadata, errorMetadata;
        int throwChildIndex=-1;
        String className="fixture.Node", resourceId="fixture:id/content";
        int refreshDelay=1000, childDelay=7;
        AccessibilityNodeInfo(String value,boolean visible) { this.value=value; this.visible=visible; }
        AccessibilityNodeInfo copy() {
            AccessibilityNodeInfo n=new AccessibilityNodeInfo(value,visible);
            n.children.addAll(children); n.throwChild=throwChild; n.refreshDelay=refreshDelay;
            n.childDelay=childDelay; n.throwMetadata=throwMetadata;
            n.throwChildIndex=throwChildIndex; n.className=className; n.resourceId=resourceId;
            n.errorMetadata=errorMetadata;
            createdCopies++; copies.add(n); return n;
        }
        void usable() { require(!recycled,"recycled node reused"); }
        int getChildCount() { usable(); return children.size(); }
        AccessibilityNodeInfo getChild(int index) {
            usable(); getterCalls++; SystemClock.now+=childDelay;
            if(throwChild || index==throwChildIndex) throw new IllegalStateException("child query failed");
            AccessibilityNodeInfo child=children.get(index); return child==null ? null : child.copy();
        }
        boolean isVisibleToUser() { usable(); return visible; }
        boolean refresh() { usable(); SystemClock.now+=refreshDelay; return true; }
        void recycle() { require(!recycled,"node recycled twice"); recycled=true; recycledCopies++; }
        int getWindowId() { usable(); return 2; }
        CharSequence getPackageName() { usable(); return "fixture.package"; }
        CharSequence getText() { usable(); return value; }
        String getViewIdResourceName() { return resourceId; }
        CharSequence getClassName() {
            if(errorMetadata) throw new AssertionError("metadata boundary error");
            if(throwMetadata) throw new IllegalStateException("metadata failed"); return className;
        }
        CharSequence getContentDescription() { return "desc"; }
        void getBoundsInScreen(Rect r) { r.left=-1; r.top=-2; r.right=110; r.bottom=220; }
        boolean isCheckable() { return false; } boolean isChecked() { return false; }
        boolean isClickable() { return true; } boolean isEnabled() { return true; }
        boolean isFocusable() { return true; } boolean isFocused() { return false; }
        boolean isScrollable() { return false; } boolean isLongClickable() { return false; }
        boolean isPassword() { return false; } boolean isSelected() { return true; }
    }
    static class AccessibilityWindowInfo {
        AccessibilityNodeInfo root;
        int rootDelay;
        boolean isActive() { return true; } boolean isFocused() { return false; }
        AccessibilityNodeInfo getRoot() {
            SystemClock.now+=rootDelay; return root==null ? null : root.copy();
        }
        int getId() { return 2; }
        void recycle() {}
    }
    static class AccessibilityServiceInfo {
        static final int FLAG_INCLUDE_NOT_IMPORTANT_VIEWS=2, FLAG_REPORT_VIEW_IDS=4, FLAG_RETRIEVE_INTERACTIVE_WINDOWS=8;
        int flags=1;
    }
    static class UiAutomation {
        static final int FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES=1;
        final AccessibilityServiceInfo service=new AccessibilityServiceInfo();
        int getServiceCalls, setServiceCalls;
        AccessibilityServiceInfo getServiceInfo() { getServiceCalls++; SystemClock.now+=20; return service; }
        void setServiceInfo(AccessibilityServiceInfo info) { require(info==service,"different service set"); setServiceCalls++; SystemClock.now+=30; }
        AccessibilityNodeInfo root;
        final List<AccessibilityWindowInfo> windows = new ArrayList<>();
        int rootDelay=3, windowDelay;
        boolean clearCache() { return true; }
        AccessibilityNodeInfo getRootInActiveWindow() {
            SystemClock.now+=rootDelay; return root==null ? null : root.copy();
        }
        List<AccessibilityWindowInfo> getWindows() {
            SystemClock.now+=windowDelay; return windows;
        }
    }
    static class JSONObject {
        static final Object NULL=new Object();
        final Map<String,Object> values=new LinkedHashMap<>();
        JSONObject put(String key,Object value) { values.put(key,value); return this; }
        static String encode(Object value) {
            if(value==null || value==NULL) return "null";
            if(value instanceof Number || value instanceof Boolean) return value.toString();
            if(value instanceof JSONObject || value instanceof JSONArray) return value.toString();
            StringBuilder encoded=new StringBuilder("\"");
            for(char c:value.toString().toCharArray()) {
                if(c=='"' || c=='\\') encoded.append('\\').append(c);
                else if(c<32) encoded.append(String.format("\\u%04x",(int)c));
                else encoded.append(c);
            }
            return encoded.append('"').toString();
        }
        public String toString() {
            StringJoiner j=new StringJoiner(",","{","}");
            for(Map.Entry<String,Object> e:values.entrySet()) j.add(encode(e.getKey())+":"+encode(e.getValue()));
            return j.toString();
        }
    }
    static class JSONArray {
        final List<Object> values=new ArrayList<>();
        JSONArray put(Object value) { values.add(value); return this; }
        public String toString() {
            StringJoiner j=new StringJoiner(",","[","]");
            for(Object v:values) j.add(JSONObject.encode(v)); return j.toString();
        }
    }
    static class Xml { static XmlSerializer newSerializer() { return new XmlSerializer(); } }
    static class XmlSerializer {
        XMLStreamWriter xml;
        void setOutput(Writer w) throws Exception { xml=XMLOutputFactory.newFactory().createXMLStreamWriter(w); }
        void startDocument(String encoding,boolean standalone) throws Exception { xml.writeStartDocument(encoding,"1.0"); }
        void startTag(String namespace,String name) throws Exception { xml.writeStartElement(name); }
        void attribute(String namespace,String name,String value) throws Exception { xml.writeAttribute(name,value); }
        void endTag(String namespace,String name) throws Exception { xml.writeEndElement(); }
        void endDocument() throws Exception { xml.writeEndDocument(); xml.flush(); }
    }
    // Boundary fault injection still delegates actual bytes/close/rename to the
    // JVM filesystem. A separate JVM consumes only the published pathname.
    static class File extends java.io.File {
        static boolean failRename;
        File(String name) { super(name); }
        File(java.io.File parent,String name) { super(parent,name); }
        public boolean renameTo(java.io.File target) { return !failRename && super.renameTo(target); }
    }
    static class FileOutputStream extends OutputStream {
        static String failSuffix, failure;
        static int syncCalls;
        final java.io.File file;
        final java.io.FileOutputStream delegate;
        boolean closed;
        FileOutputStream(java.io.File file) throws IOException { this.file=file; delegate=new java.io.FileOutputStream(file); }
        void fault(String kind) throws IOException {
            if(kind.equals(failure) && failSuffix!=null && file.getName().endsWith(failSuffix)) throw new IOException(kind+" failed");
        }
        public void write(int b) throws IOException { fault("write"); delegate.write(b); }
        public void write(byte[] b,int start,int count) throws IOException { fault("write"); delegate.write(b,start,count); }
        public void flush() throws IOException { fault("flush"); delegate.flush(); }
        public void close() throws IOException {
            if(closed) return;
            closed=true; delegate.close();
            if(file.getName().endsWith(".json.tmp")) {
                java.io.File target=new java.io.File(file.getParentFile(),file.getName().substring(0,file.getName().length()-4));
                childRead("missing",target.getPath(),"");
            }
            fault("close");
        }
        SyncTrap getFD() { return new SyncTrap(); }
        static class SyncTrap { void sync() { syncCalls++; throw new AssertionError("ephemeral transport performed physical-disk sync"); } }
    }
    final Context context=new Context();
    final UiAutomation automation=new UiAutomation();
    Bundle finished;
    int finishCode=123;
    boolean startRequested;
    boolean failSession;
    int noticeCalls;
    boolean failNotice;
    String expectedNoticeBasename, expectedNoticeContent, expectedNoticeTimeKey;
    Bundle expectedNoticeDiagnostics;
    final List<Bundle> notices=new ArrayList<>();
    Context getContext() { return context; }
    void start() { startRequested=true; }
    UiAutomation getUiAutomation(int flags) {
        require(flags==UiAutomation.FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES,"accessibility service suppression changed");
        SystemClock.now+=50; return automation;
    }
    void finish(int code,Bundle result) { finishCode=code; finished=result; }
    void expectNotice(String basename,String content,Bundle diagnostics,String timeKey) {
        expectedNoticeBasename=basename; expectedNoticeContent=content;
        expectedNoticeDiagnostics=diagnostics; expectedNoticeTimeKey=timeKey;
    }
    void sendStatus(int code,Bundle notice) {
        noticeCalls++;
        require(code==1 && notice.keySet().size()==1,"notification status schema changed");
        require(("{\"protocol\":1,\"nonce\":\""+NONCE+"\",\"basename\":\""+expectedNoticeBasename+"\"}")
                .equals(notice.getString("luoshu_snapshot_published")),"notification envelope changed");
        require(expectedNoticeDiagnostics.getString(expectedNoticeTimeKey)!=null,
                "notification preceded publication timestamp");
        String timingPrefix=expectedNoticeBasename.equals("ready.json") ? "helper_ready_notice" : "helper_last_response_notice";
        String started=expectedNoticeDiagnostics.getString(timingPrefix+"_started_uptime_ms");
        require(started!=null && Long.parseLong(started)>=Long.parseLong(expectedNoticeDiagnostics.getString(expectedNoticeTimeKey)),
                "notice-start timestamp preceded private publication");
        require(expectedNoticeDiagnostics.getString(timingPrefix+"_finished_uptime_ms")==null,
                "notice-finish timestamp preceded callback return");
        require(!new File(context.directory,expectedNoticeBasename+".tmp").exists(),
                "notification preceded private rename");
        try {
            childRead("json",new File(context.directory,expectedNoticeBasename).getPath(),expectedNoticeContent);
        } catch(IOException error) { throw new UncheckedIOException(error); }
        SystemClock.now+=5;
        if(failNotice) throw new IllegalStateException("notification failed");
        notices.add(notice);
    }
    static void refreshLegacyAccessibilityCache(UiAutomation a,Bundle r,long deadline) { throw new AssertionError("unexpected legacy branch"); }
    Bundle runSession(String nonce,Bundle diagnostics) {
        if(failSession) throw new IllegalStateException("session failure");
        snapshotDiagnostics(diagnostics,snapshot(automation,"hierarchy-0099.xml",context.directory,diagnostics));
        Bundle result=new Bundle(); result.putString("session","finished"); return result;
    }
    static void require(boolean ok,String message) { if(!ok) throw new AssertionError(message); }
    static void childRead(String mode,String path,String expected) throws IOException {
        try {
            Process p=new ProcessBuilder(System.getProperty("java.home")+"/bin/java","-cp",System.getProperty("java.class.path"),
                    "NativeSnapshotPublicationHarness",mode,path,expected).redirectErrorStream(true).start();
            require(p.waitFor(10,java.util.concurrent.TimeUnit.SECONDS),"cross-process read timed out");
            String output=new String(p.getInputStream().readAllBytes(),StandardCharsets.UTF_8);
            require(p.exitValue()==0,"cross-process "+mode+" failed: "+output);
        } catch(InterruptedException e) { throw new IOException(e); }
    }
    static void reader(String mode,String path,String expected) throws Exception {
        java.io.File file=new java.io.File(path);
        if(mode.equals("missing")) { require(!file.exists(),"temporary content advertised as ready"); return; }
        if(mode.equals("json")) {
            require(expected.equals(Files.readString(file.toPath(),StandardCharsets.UTF_8)),"incomplete published JSON"); return;
        }
        Document doc=DocumentBuilderFactory.newInstance().newDocumentBuilder().parse(file);
        require("hierarchy".equals(doc.getDocumentElement().getTagName()),"incomplete hierarchy");
        require("1".equals(doc.getDocumentElement().getAttribute("rotation")),"rotation changed");
        NodeList nodes=doc.getElementsByTagName("node");
        require(nodes.getLength()==3,"hidden/null node exported or visible descendant missing");
        Element root=(Element)nodes.item(0), child=(Element)nodes.item(1), leaf=(Element)nodes.item(2);
        require("root".equals(root.getAttribute("text")),"root fields changed");
        require("A<&\"😀".equals(child.getAttribute("text")),"XML escaping/sanitization changed");
        require("1".equals(child.getAttribute("index")),"child index no longer original index");
        require("leaf".equals(leaf.getAttribute("text")) && "true".equals(leaf.getAttribute("selected")),"live attributes changed");
        require("[0,0][100,200]".equals(leaf.getAttribute("bounds")),"display bounds clipping changed");
    }
    static AccessibilityNodeInfo tree() {
        AccessibilityNodeInfo root=new AccessibilityNodeInfo("root",true);
        root.children.add(null);
        AccessibilityNodeInfo child=new AccessibilityNodeInfo("A<&\"😀\u0001",true);
        child.children.add(new AccessibilityNodeInfo("leaf",true)); root.children.add(child);
        root.children.add(new AccessibilityNodeInfo("hidden",false)); return root;
    }
    static void clearFaults() { File.failRename=false; FileOutputStream.failure=null; FileOutputStream.failSuffix=null; }
    static void allCopiesRecycled() {
        for(AccessibilityNodeInfo copy:AccessibilityNodeInfo.copies) require(copy.recycled,"retained node leaked");
    }
    static JSONObject lastQuery(NativeSnapshotPublicationHarness h) { return h.childQueryRecords.getLast(); }
    static void checkNoticeTimes(Bundle diagnostics,String prefix,String publishedKey) {
        long published=Long.parseLong(diagnostics.getString(publishedKey));
        long started=Long.parseLong(diagnostics.getString(prefix+"_started_uptime_ms"));
        long finished=Long.parseLong(diagnostics.getString(prefix+"_finished_uptime_ms"));
        require(published<=started && finished==started+5,"notice timing lost order or watcher duration");
    }
    static void expectJsonFailure(NativeSnapshotPublicationHarness h,File dir,String filename,String failure) throws Exception {
        int before=h.noticeCalls;
        FileOutputStream.failure=failure; FileOutputStream.failSuffix=".json.tmp";
        try { h.publishJson(dir,filename,new JSONObject().put("state","ready"),NONCE,new Bundle(),"published"); throw new AssertionError("JSON failure accepted"); }
        catch(IOException expected) { require(!new File(dir,filename).exists(),"failed JSON was advertised"); }
        require(h.noticeCalls==before,"failed private publication sent a notification");
        clearFaults();
    }
    public static void main(String[] args) throws Exception {
        if(!args[0].equals("exercise")) { reader(args[0],args[1],args[2]); return; }
        File dir=new File(args[1]); require(dir.mkdir(),"cannot create fresh test directory");
        NativeSnapshotPublicationHarness h=new NativeSnapshotPublicationHarness();
        h.context.directory=dir;
        SystemClock.now=100;
        h.onCreate(new Bundle());
        require(h.startRequested && "100".equals(h.lifecycleDiagnostics.getString("helper_on_create_started_uptime_ms")) &&
                "50".equals(h.lifecycleDiagnostics.getString("helper_process_started_uptime_ms")),"public process/create lifecycle lost");
        NativeSnapshotPublicationHarness legacy=new NativeSnapshotPublicationHarness(); Build.VERSION.SDK_INT=23;
        legacy.onCreate(new Bundle()); Build.VERSION.SDK_INT=34;
        require(legacy.lifecycleDiagnostics.getString("helper_process_started_uptime_ms")==null &&
                "unavailable-before-api24".equals(legacy.lifecycleDiagnostics.getString("helper_process_start_time_status")),
                "old API invented process uptime");
        Bundle connectDiagnostics=new Bundle();
        h.connectAutomation(connectDiagnostics);
        require("100".equals(connectDiagnostics.getString("helper_automation_connect_started_uptime_ms")) &&
                "150".equals(connectDiagnostics.getString("helper_automation_connected_uptime_ms")) &&
                "200".equals(connectDiagnostics.getString("helper_automation_configured_uptime_ms")) &&
                h.automation.getServiceCalls==1 && h.automation.setServiceCalls==1 && h.automation.service.flags==15,
                "connect/config clocks or original service call count changed");
        JSONObject ready=new JSONObject().put("protocol",1).put("nonce",NONCE).put("state","ready").put("text","雪😀");
        Bundle readyDiagnostics=new Bundle();
        h.expectNotice("ready.json",ready.toString(),readyDiagnostics,"helper_ready_published_uptime_ms");
        h.publishJson(dir,"ready.json",ready,NONCE,readyDiagnostics,"helper_ready_published_uptime_ms");
        require(h.notices.size()==1,"ready publication sent no matching notification");
        checkNoticeTimes(readyDiagnostics,"helper_ready_notice","helper_ready_published_uptime_ms");
        readyDiagnostics.putString("helper_last_response_notice_started_uptime_ms","1");
        readyDiagnostics.putString("helper_last_response_notice_finished_uptime_ms","2");
        acceptRequestDiagnostics(readyDiagnostics,"11111111111111111111111111111111","hierarchy-0001.xml");
        require(!readyDiagnostics.containsKey("helper_last_response_notice_started_uptime_ms") &&
                !readyDiagnostics.containsKey("helper_last_response_notice_finished_uptime_ms"),"previous request's notice timings survived acceptance");
        checkNoticeTimes(readyDiagnostics,"helper_ready_notice","helper_ready_published_uptime_ms");
        childRead("json",new File(dir,"ready.json").getPath(),ready.toString());
        require(!new File(dir,"ready.json.tmp").exists(),"temporary file remained after publication");
        try { h.publishJson(dir,"ready.json",ready,NONCE,new Bundle(),"published"); throw new AssertionError("reused published file accepted"); }
        catch(IllegalStateException expected) {}
        Files.writeString(new File(dir,"old.json.tmp").toPath(),"partial");
        try { h.publishJson(dir,"old.json",ready,NONCE,new Bundle(),"published"); throw new AssertionError("reused temporary file accepted"); }
        catch(IllegalStateException expected) { require(!new File(dir,"old.json").exists(),"partial file published"); }
        expectJsonFailure(h,dir,"write-failed.json","write"); expectJsonFailure(h,dir,"close-failed.json","close");
        File.failRename=true;
        try { h.publishJson(dir,"rename-failed.json",ready,NONCE,new Bundle(),"published"); throw new AssertionError("failed rename accepted"); }
        catch(IllegalStateException expected) { require(!new File(dir,"rename-failed.json").exists(),"failed rename published"); }
        require(h.noticeCalls==1,"failed/reused private publication sent a notification");
        clearFaults();
        h.context.directory=dir; h.automation.root=tree();
        Bundle diagnostics=new Bundle();
        Bundle result=h.snapshot(h.automation,"hierarchy-0001.xml",dir,diagnostics);
        require("ok".equals(result.getString("snapshot")),"complete snapshot failed: "+result.getString("error"));
        childRead("xml",new File(dir,"hierarchy-0001.xml").getPath(),"");
        require("3".equals(result.getString("nodes")),"node count changed");
        require("6".equals(result.getString("child_query_count")) && "42".equals(result.getString("child_query_ms")),"actual root/export query attribution changed");
        require("3".equals(result.getString("export_child_query_count")) && "21".equals(result.getString("export_child_query_ms")) &&
                "1".equals(result.getString("observed_child_reuse_count")),"accepted visible direct child was requeried");
        int optimizedCalls=AccessibilityNodeInfo.getterCalls;
        OBSERVED_CHILD_LIMIT=0;
        Bundle baseline=h.snapshot(h.automation,"hierarchy-0012.xml",dir,new Bundle()); OBSERVED_CHILD_LIMIT=32;
        require("7".equals(baseline.getString("child_query_count")) && "49".equals(baseline.getString("child_query_ms")) &&
                "4".equals(baseline.getString("export_child_query_count")),"bound-zero requery fallback did not reproduce baseline");
        require(AccessibilityNodeInfo.getterCalls-optimizedCalls==7 && optimizedCalls==6,"diagnostics added a getter query");
        require(Arrays.equals(Files.readAllBytes(new File(dir,"hierarchy-0001.xml").toPath()),
                Files.readAllBytes(new File(dir,"hierarchy-0012.xml").toPath())),"reuse changed complete XML bytes");
        allCopiesRecycled();
        long previous=0;
        for(String phase:new String[]{"export_started","export_serialization_started","export_serialization_finished","export_flush_started","export_flush_finished","export_close_started","export_close_finished","export_finished"}) {
            long at=Long.parseLong(diagnostics.getString("helper_last_"+phase+"_uptime_ms"));
            require(at>=previous,"export diagnostic clocks/order changed"); previous=at;
        }
        require(diagnostics.keySet().size()<25,"per-call records leaked into per-phase keys");
        String responseName="response-11111111111111111111111111111111.json";
        JSONObject response=new JSONObject().put("protocol",1).put("nonce",NONCE).put("request_id","11111111111111111111111111111111")
                .put("filename","hierarchy-0001.xml").put("root_wait_ms",8000).put("code",-1);
        h.expectNotice(responseName,response.toString(),diagnostics,"helper_last_response_published_uptime_ms");
        h.publishJson(dir,responseName,response,NONCE,diagnostics,"helper_last_response_published_uptime_ms");
        require(h.notices.size()==2,"response publication sent no matching notification");
        checkNoticeTimes(diagnostics,"helper_last_response_notice","helper_last_response_published_uptime_ms");
        String noticeFailureName="response-22222222222222222222222222222222.json";
        Bundle noticeFailureDiagnostics=new Bundle();
        h.expectNotice(noticeFailureName,response.toString(),noticeFailureDiagnostics,"published");
        h.failNotice=true;
        try { h.publishJson(dir,noticeFailureName,response,NONCE,noticeFailureDiagnostics,"published"); throw new AssertionError("notification exception hidden"); }
        catch(IllegalStateException expected) { require("notification failed".equals(expected.getMessage()),"notification failure changed"); }
        require(new File(dir,noticeFailureName).exists() && noticeFailureDiagnostics.getString("published")!=null,
                "notification exception disguised successful private publication");
        require(h.noticeCalls==3 && h.notices.size()==2,"notification failure was accepted as delivery");
        checkNoticeTimes(noticeFailureDiagnostics,"helper_last_response_notice","published");
        h.failNotice=false;
        for(String fault:new String[]{"write","flush","close"}) {
            FileOutputStream.failure=fault; FileOutputStream.failSuffix=".xml";
            Bundle failed=h.snapshot(h.automation,"hierarchy-000"+(fault.equals("write")?2:fault.equals("flush")?3:4)+".xml",dir,new Bundle());
            require("failed".equals(failed.getString("snapshot")) && failed.getString("filename")==null,"failed export became successful");
            clearFaults();
        }
        h.automation.root=new AccessibilityNodeInfo("root-only",true); h.automation.rootDelay=3000; h.automation.windowDelay=1000;
        Bundle rootOnly=h.snapshot(h.automation,"hierarchy-0005.xml",dir,new Bundle());
        require("failed".equals(rootOnly.getString("snapshot")) && !new File(dir,"hierarchy-0005.xml").exists(),"root-only content accepted");
        h.automation.root.children.add(new AccessibilityNodeInfo("invisible",false));
        Bundle invisible=h.snapshot(h.automation,"hierarchy-0006.xml",dir,new Bundle());
        require("failed".equals(invisible.getString("snapshot")) && !new File(dir,"hierarchy-0006.xml").exists(),"invisible descendants accepted");
        h.automation.root=tree(); h.automation.rootDelay=8000;
        Bundle late=h.snapshot(h.automation,"hierarchy-0007.xml",dir,new Bundle());
        require("failed".equals(late.getString("snapshot")) && !new File(dir,"hierarchy-0007.xml").exists(),"late root expanded original deadline");
        require("0".equals(late.getString("child_query_count")),"late active root queried descendants");
        h.automation.root=null; h.automation.rootDelay=3; h.automation.windowDelay=0;
        AccessibilityWindowInfo window=new AccessibilityWindowInfo(); window.root=tree(); window.rootDelay=8000;
        h.automation.windows.add(window);
        Bundle lateWindow=h.snapshot(h.automation,"hierarchy-0010.xml",dir,new Bundle());
        require("failed".equals(lateWindow.getString("snapshot")) && "0".equals(lateWindow.getString("child_query_count"))
                && !new File(dir,"hierarchy-0010.xml").exists(),"late window root queried descendants or became evidence");
        h.automation.windows.clear();
        h.automation.root=new AccessibilityNodeInfo("incomplete",true); h.automation.root.refreshDelay=8000;
        h.automation.root.children.add(new AccessibilityNodeInfo("invisible",false));
        Bundle lateRefresh=h.snapshot(h.automation,"hierarchy-0011.xml",dir,new Bundle());
        require("failed".equals(lateRefresh.getString("snapshot")) && "1".equals(lateRefresh.getString("child_query_count"))
                && "1".equals(lateRefresh.getString("root_refresh_attempts")) && !new File(dir,"hierarchy-0011.xml").exists(),
                "late retained-root refresh queried descendants or became evidence");
        h.automation.root=tree(); h.automation.root.throwChild=true; h.automation.rootDelay=3;
        Bundle queryFailure=h.snapshot(h.automation,"hierarchy-0008.xml",dir,new Bundle());
        require("failed".equals(queryFailure.getString("snapshot")) && "1".equals(queryFailure.getString("child_query_count")) && "7".equals(queryFailure.getString("child_query_ms")),"throwing query attribution/error lost");
        require("1".equals(queryFailure.getString("child_query_thrown_count")) &&
                "threw".equals(lastQuery(h).values.get("outcome")) &&
                "java.lang.IllegalStateException".equals(lastQuery(h).values.get("exception")),"getter exception evidence lost");
        h.automation.root=new AccessibilityNodeInfo("slow-visible",true);
        h.automation.root.children.add(new AccessibilityNodeInfo("visible",true));
        h.automation.root.children.add(new AccessibilityNodeInfo("must-not-query",true));
        h.automation.root.throwChildIndex=1; h.automation.root.childDelay=8000;
        int beforeSlow=AccessibilityNodeInfo.getterCalls;
        Bundle slowVisible=h.snapshot(h.automation,"hierarchy-0013.xml",dir,new Bundle());
        require("failed".equals(slowVisible.getString("snapshot")) && !new File(dir,"hierarchy-0013.xml").exists() &&
                Boolean.TRUE.equals(lastQuery(h).values.get("finished_at_or_after_root_deadline")),"slow successful child relaxed original deadline");
        require(AccessibilityNodeInfo.getterCalls-beforeSlow==1 && "1".equals(slowVisible.getString("child_query_nonnull_count")),
                "diagnostic duplicated actual late getters");
        require("true".equals(slowVisible.getString("last_root_observation_partial")) &&
                "1".equals(slowVisible.getString("last_root_examined_child_count")) &&
                "2".equals(slowVisible.getString("last_root_child_count")) &&
                "true".equals(slowVisible.getString("last_root_observation_deadline_reached")) &&
                h.observedChildren.isEmpty() && h.observedRoot==null,"late child observation continued or retention survived rejection");
        require("8000".equals(slowVisible.getString("child_query_max_ms")),"slow getter max lost");
        allCopiesRecycled();
        h.automation.root=new AccessibilityNodeInfo("slow-null",true);
        h.automation.root.children.add(null); h.automation.root.children.add(new AccessibilityNodeInfo("must-not-query",true));
        h.automation.root.throwChildIndex=1; h.automation.root.childDelay=8000;
        beforeSlow=AccessibilityNodeInfo.getterCalls;
        Bundle lateNull=h.snapshot(h.automation,"hierarchy-0017.xml",dir,new Bundle());
        require("failed".equals(lateNull.getString("snapshot")) && "1".equals(lateNull.getString("child_query_null_count")) &&
                "true".equals(lateNull.getString("last_root_observation_partial")) && AccessibilityNodeInfo.getterCalls-beforeSlow==1 &&
                "null".equals(lastQuery(h).values.get("outcome")) && Boolean.TRUE.equals(lastQuery(h).values.get("finished_at_or_after_root_deadline")) &&
                !new File(dir,"hierarchy-0017.xml").exists(),"late null started another child or became XML evidence");
        allCopiesRecycled();
        h.automation.root=new AccessibilityNodeInfo("slow-throw",true);
        h.automation.root.children.add(null); h.automation.root.throwChild=true; h.automation.root.childDelay=9000;
        Bundle lateThrow=h.snapshot(h.automation,"hierarchy-0018.xml",dir,new Bundle());
        require("failed".equals(lateThrow.getString("snapshot")) && "1".equals(lateThrow.getString("child_query_thrown_count")) &&
                "threw".equals(lastQuery(h).values.get("outcome")) && Long.valueOf(9000).equals(lastQuery(h).values.get("duration_ms")) &&
                Boolean.TRUE.equals(lastQuery(h).values.get("finished_at_or_after_root_deadline")) && !new File(dir,"hierarchy-0018.xml").exists(),
                "late throwing getter lost real exception/duration or became XML");
        allCopiesRecycled();
        h.childQueryRecords.clear(); h.childQueryCount=0; h.childQueryMillis=0;
        AccessibilityNodeInfo nullParent=new AccessibilityNodeInfo("null-parent",true);
        nullParent.children.add(null); nullParent.childDelay=5000;
        h.readChild(nullParent,0,"export",0);
        require("null".equals(lastQuery(h).values.get("outcome")) &&
                Long.valueOf(5000).equals(lastQuery(h).values.get("duration_ms")),"slow null getter evidence lost");
        nullParent.throwChild=true;
        try { h.readChild(nullParent,0,"export",0); throw new AssertionError("slow throwing getter hidden"); }
        catch(IllegalStateException expected) { require("child query failed".equals(expected.getMessage()),"diagnostics replaced original getter exception"); }
        require("threw".equals(lastQuery(h).values.get("outcome")) &&
                Long.valueOf(5000).equals(lastQuery(h).values.get("duration_ms")),"slow exception getter evidence lost");
        AccessibilityNodeInfo metadataParent=new AccessibilityNodeInfo("metadata-parent",true);
        metadataParent.children.add(new AccessibilityNodeInfo("returned",true)); metadataParent.throwMetadata=true;
        int beforeMetadata=AccessibilityNodeInfo.getterCalls;
        AccessibilityNodeInfo returned=h.readChild(metadataParent,0,"export",0);
        require(returned!=null && AccessibilityNodeInfo.getterCalls==beforeMetadata+1 &&
                "failed".equals(lastQuery(h).values.get("metadata_status")),"diagnostic failure replaced getter result or repeated query");
        returned.recycle();
        metadataParent.throwChild=true;
        try { h.readChild(metadataParent,0,"export",0); throw new AssertionError("metadata failure hid real getter failure"); }
        catch(IllegalStateException expected) { require("child query failed".equals(expected.getMessage()),"metadata failure replaced actual exception"); }
        require("java.lang.IllegalStateException".equals(lastQuery(h).values.get("exception")),"metadata failure erased exception type");
        metadataParent.throwChild=false; metadataParent.throwMetadata=false; metadataParent.errorMetadata=true;
        returned=h.readChild(metadataParent,0,"export",0);
        require(returned!=null && "failed".equals(lastQuery(h).values.get("metadata_status")),"diagnostic boundary Error replaced getter return");
        returned.recycle();
        AccessibilityNodeInfo escapedParent=new AccessibilityNodeInfo("escaped",true);
        escapedParent.children.add(null);
        escapedParent.className="\u0000".repeat(300); escapedParent.resourceId="\\\"".repeat(150);
        h.readChild(escapedParent,0,"export",0);
        require(lastQuery(h).toString().length()<2048 && Boolean.TRUE.equals(
                ((JSONObject)lastQuery(h).values.get("parent")).values.get("fields_truncated")),"metadata bound lost complete record JSON");
        System.out.println("BOUNDED_METADATA_JSON="+lastQuery(h));
        AccessibilityNodeInfo firstRoot=tree(), otherRoot=tree();
        h.childRootDeadline=SystemClock.now+8000;
        h.observeRoot(new Bundle(),new JSONArray(),firstRoot,"first",SystemClock.now);
        require(h.takeObservedChild(otherRoot,1)==null,"retained child crossed root identity");
        h.observeRoot(new Bundle(),new JSONArray(),otherRoot,"next",SystemClock.now);
        require(h.takeObservedChild(firstRoot,1)==null,"new observation kept previous root retention");
        AccessibilityNodeInfo retained=h.takeObservedChild(otherRoot,1); require(retained!=null,"new exact-root retention missing"); retained.recycle();
        h.clearObservedChildren(); allCopiesRecycled();
        h.automation.root=new AccessibilityNodeInfo("partial-observation",true);
        h.automation.root.children.add(new AccessibilityNodeInfo("retained-before-throw",true));
        h.automation.root.children.add(new AccessibilityNodeInfo("throws",true)); h.automation.root.throwChildIndex=1;
        Bundle partial=h.snapshot(h.automation,"hierarchy-0016.xml",dir,new Bundle());
        require("failed".equals(partial.getString("snapshot")) && "2".equals(partial.getString("child_query_count")) &&
                !new File(dir,"hierarchy-0016.xml").exists(),"partial retained observation survived query failure");
        allCopiesRecycled();
        h.automation.root=new AccessibilityNodeInfo("many",true); h.automation.root.childDelay=1;
        for(int i=0;i<40;i++) h.automation.root.children.add(new AccessibilityNodeInfo("item"+i,true));
        Bundle bounded=h.snapshot(h.automation,"hierarchy-0014.xml",dir,new Bundle());
        require("ok".equals(bounded.getString("snapshot")) && "48".equals(bounded.getString("child_query_count")) &&
                "8".equals(bounded.getString("export_child_query_count")) && "32".equals(bounded.getString("observed_child_reuse_count")),
                "bounded retention did not fall back to real overflow queries");
        require(h.childQueryRecords.size()==32 && "16".equals(bounded.getString("child_query_records_omitted")) &&
                Integer.valueOf(17).equals(h.childQueryRecords.getFirst().values.get("sequence")) &&
                Integer.valueOf(48).equals(lastQuery(h).values.get("sequence")),"bounded last-call retention lost distribution or omitted count");
        Bundle boundedDiagnostics=new Bundle(); snapshotDiagnostics(boundedDiagnostics,bounded);
        require(bounded.getString("child_query_records").length()>1024 && bounded.getString("child_query_records").equals(
                boundedDiagnostics.getString("helper_last_snapshot_child_query_records")),"complete record JSON was truncated");
        System.out.println("DIAGNOSTIC_JSON="+bounded.getString("child_query_records"));
        acceptRequestDiagnostics(boundedDiagnostics,"fresh","hierarchy-0015.xml");
        require(!boundedDiagnostics.containsKey("helper_last_snapshot_child_query_records"),"new request retained old getter JSON");
        h.automation.root=tree(); h.automation.root.childDelay=7;
        Bundle reset=h.snapshot(h.automation,"hierarchy-0015.xml",dir,new Bundle());
        require("6".equals(reset.getString("child_query_count")) && "0".equals(reset.getString("child_query_records_omitted")) &&
                "7".equals(reset.getString("child_query_max_ms")) && h.childQueryRecords.size()==6,"getter metrics crossed requests");
        allCopiesRecycled();
        h.automation.root.throwChild=true;
        h.arguments.putString("session_nonce","test-session"); h.onStart();
        require(h.finishCode==-1 && "finished".equals(h.finished.getString("session")) && "failed".equals(h.finished.getString("helper_last_snapshot_status")),"failed snapshot changed normal session close");
        require("1".equals(h.finished.getString("helper_last_snapshot_child_query_count")) &&
                "7".equals(h.finished.getString("helper_last_snapshot_child_query_ms")) &&
                h.finished.getString("helper_last_snapshot_export_child_query_count")==null,
                "final failed-request query diagnostics missing or mixed with previous export");
        require(h.finished.getString("helper_on_start_started_uptime_ms")!=null &&
                "50".equals(h.finished.getString("helper_process_started_uptime_ms")),"lifecycle was not carried into final result");
        for(Map.Entry<String,String> entry:h.finished.values.entrySet()) require(entry.getValue().length()<=
                (entry.getKey().equals("helper_last_snapshot_child_query_records")?70000:1024),"unbounded final diagnostic string");
        JSONObject closed=new JSONObject().put("state","closed");
        writeJson(dir,"closed.json",closed); childRead("json",new File(dir,"closed.json").getPath(),closed.toString());
        h.failSession=true; h.onStart(); require(h.finishCode==0 && "failed".equals(h.finished.getString("snapshot")),"real session failure changed close code");
        require(FileOutputStream.syncCalls==0,"ephemeral publication forced durability");
        System.out.println("Passed production Java cross-process publication, export failures, deadlines and diagnostics");
        System.out.println("Compared complete XML: same-production bound-zero requery 7 getters/49 ms; retained child 6 getters/42 ms; overflow 48 getters, 32 reused, last32 records/16 omitted");
    }
''' + methods + '\n}\n'
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            file = directory / 'NativeSnapshotPublicationHarness.java'
            file.write_text(harness)
            process_boundary = directory / 'android' / 'os' / 'Process.java'
            process_boundary.parent.mkdir(parents=True)
            process_boundary.write_text('package android.os; public class Process { public static long getStartUptimeMillis() { return 50; } }')
            def capture(name, result):
                if destination := os.environ.get('LUOSHU_NATIVE_TEST_EVIDENCE_DIR'):
                    evidence = Path(destination)
                    evidence.mkdir(parents=True, exist_ok=True)
                    (evidence / f'{name}-stdout.bin').write_bytes(result.stdout)
                    (evidence / f'{name}-stderr.bin').write_bytes(result.stderr)
                    if name == 'javac':
                        (evidence / file.name).write_bytes(file.read_bytes())
                        (evidence / 'ProcessBoundary.java').write_bytes(process_boundary.read_bytes())
                    else:
                        for filename, label in [('hierarchy-0001.xml', 'retained-fixture.xml'),
                                                ('hierarchy-0012.xml', 'bound-zero-fixture.xml')]:
                            (evidence / label).write_bytes((directory / 'session' / filename).read_bytes())
            compiled = subprocess.run([java, '--module', 'jdk.compiler/com.sun.tools.javac.Main',
                                       '-d', str(directory), str(file), str(process_boundary)], capture_output=True, timeout=30)
            capture('javac', compiled)
            self.assertEqual(0, compiled.returncode, compiled.stderr.decode())
            exercised = subprocess.run([java, '-cp', str(directory), 'NativeSnapshotPublicationHarness',
                                        'exercise', str(directory / 'session')],
                                       capture_output=True, timeout=30)
            capture('java', exercised)
            self.assertEqual(0, exercised.returncode, exercised.stderr.decode())
            for line in exercised.stdout.decode().splitlines():
                if line.startswith('DIAGNOSTIC_JSON='):
                    records = json.loads(line.partition('=')[2])
                    self.assertEqual(32, len(records))
                    self.assertEqual(list(range(17, 49)), [record['sequence'] for record in records])
                    self.assertLess(len(line.partition('=')[2]), 70000)
                elif line.startswith('BOUNDED_METADATA_JSON='):
                    record = json.loads(line.partition('=')[2])
                    self.assertEqual('null', record['outcome'])
                    self.assertTrue(record['parent']['fields_truncated'])
                    self.assertLess(len(line.partition('=')[2]), 2048)
                else:
                    print(line)
            self.assertIn('Passed production Java cross-process publication, export failures, deadlines and diagnostics',
                          exercised.stdout.decode())


if __name__ == '__main__':
    unittest.main()
