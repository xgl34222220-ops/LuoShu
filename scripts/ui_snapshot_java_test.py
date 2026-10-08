#!/usr/bin/env python3
"""Run production Java snapshot/file code with deterministic Android boundaries.

The JVM writes real files and independent JVM readers verify complete JSON/XML.
Node fixtures exercise rejection/export mechanics; they are not device evidence.
"""
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

        def method(signature):
            start = source.index(signature)
            return source[start:source.index('\n    }', start) + len('\n    }')]

        methods = '\n'.join(method(signature) for signature in (
            '    public void onStart()',
            '    private static void lastDiagnostic(',
            '    private static void lastDiagnosticTime(',
            '    private static void rootQueryStarted(',
            '    private static void rootQueryReturned(',
            '    private static void snapshotDiagnostics(',
            '    private static void writeJson(',
            '    private Bundle snapshot(',
            '    private int observeRoot(',
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
public class NativeSnapshotPublicationHarness {
    private Bundle arguments = new Bundle();
    private int nodeCount, childQueryCount;
    private long childQueryMillis;
    private static final int ROOT_WAIT_MS = 8000;
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
        static class VERSION { static final int SDK_INT=34; }
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
        final String value;
        final boolean visible;
        final List<AccessibilityNodeInfo> children = new ArrayList<>();
        boolean recycled, throwChild;
        AccessibilityNodeInfo(String value,boolean visible) { this.value=value; this.visible=visible; }
        AccessibilityNodeInfo copy() {
            AccessibilityNodeInfo n=new AccessibilityNodeInfo(value,visible);
            n.children.addAll(children); n.throwChild=throwChild; return n;
        }
        void usable() { require(!recycled,"recycled node reused"); }
        int getChildCount() { usable(); return children.size(); }
        AccessibilityNodeInfo getChild(int index) {
            usable(); SystemClock.now+=7;
            if(throwChild) throw new IllegalStateException("child query failed");
            AccessibilityNodeInfo child=children.get(index); return child==null ? null : child.copy();
        }
        boolean isVisibleToUser() { usable(); return visible; }
        boolean refresh() { usable(); SystemClock.now+=1000; return true; }
        void recycle() { require(!recycled,"node recycled twice"); recycled=true; }
        int getWindowId() { usable(); return 2; }
        CharSequence getPackageName() { usable(); return "fixture.package"; }
        CharSequence getText() { usable(); return value; }
        String getViewIdResourceName() { return "fixture:id/content"; }
        CharSequence getClassName() { return "fixture.Node"; }
        CharSequence getContentDescription() { return "desc"; }
        void getBoundsInScreen(Rect r) { r.left=-1; r.top=-2; r.right=110; r.bottom=220; }
        boolean isCheckable() { return false; } boolean isChecked() { return false; }
        boolean isClickable() { return true; } boolean isEnabled() { return true; }
        boolean isFocusable() { return true; } boolean isFocused() { return false; }
        boolean isScrollable() { return false; } boolean isLongClickable() { return false; }
        boolean isPassword() { return false; } boolean isSelected() { return true; }
    }
    static class AccessibilityWindowInfo {
        boolean isActive() { return false; } boolean isFocused() { return false; }
        AccessibilityNodeInfo getRoot() { return null; } int getId() { return 2; }
        void recycle() {}
    }
    static class UiAutomation {
        AccessibilityNodeInfo root;
        int rootDelay=3, windowDelay;
        boolean clearCache() { return true; }
        AccessibilityNodeInfo getRootInActiveWindow() {
            SystemClock.now+=rootDelay; return root==null ? null : root.copy();
        }
        List<AccessibilityWindowInfo> getWindows() {
            SystemClock.now+=windowDelay; return Collections.emptyList();
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
            String s=value.toString();
            return "\""+s.replace("\\","\\\\").replace("\"","\\\"").replace("\n","\\n")+"\"";
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
    boolean failSession;
    Context getContext() { return context; }
    UiAutomation connectAutomation(Bundle diagnostics) { return automation; }
    void finish(int code,Bundle result) { finishCode=code; finished=result; }
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
    static void expectJsonFailure(File dir,String filename,String failure) throws Exception {
        FileOutputStream.failure=failure; FileOutputStream.failSuffix=".json.tmp";
        try { writeJson(dir,filename,new JSONObject().put("state","ready")); throw new AssertionError("JSON failure accepted"); }
        catch(IOException expected) { require(!new File(dir,filename).exists(),"failed JSON was advertised"); }
        clearFaults();
    }
    public static void main(String[] args) throws Exception {
        if(!args[0].equals("exercise")) { reader(args[0],args[1],args[2]); return; }
        File dir=new File(args[1]); require(dir.mkdir(),"cannot create fresh test directory");
        JSONObject ready=new JSONObject().put("protocol",1).put("nonce","0123456789abcdef0123456789abcdef").put("state","ready").put("text","雪😀");
        writeJson(dir,"ready.json",ready);
        childRead("json",new File(dir,"ready.json").getPath(),ready.toString());
        require(!new File(dir,"ready.json.tmp").exists(),"temporary file remained after publication");
        try { writeJson(dir,"ready.json",ready); throw new AssertionError("reused published file accepted"); }
        catch(IllegalStateException expected) {}
        Files.writeString(new File(dir,"old.json.tmp").toPath(),"partial");
        try { writeJson(dir,"old.json",ready); throw new AssertionError("reused temporary file accepted"); }
        catch(IllegalStateException expected) { require(!new File(dir,"old.json").exists(),"partial file published"); }
        expectJsonFailure(dir,"write-failed.json","write"); expectJsonFailure(dir,"close-failed.json","close");
        File.failRename=true;
        try { writeJson(dir,"rename-failed.json",ready); throw new AssertionError("failed rename accepted"); }
        catch(IllegalStateException expected) { require(!new File(dir,"rename-failed.json").exists(),"failed rename published"); }
        clearFaults();
        NativeSnapshotPublicationHarness h=new NativeSnapshotPublicationHarness();
        h.context.directory=dir; h.automation.root=tree();
        Bundle diagnostics=new Bundle();
        Bundle result=h.snapshot(h.automation,"hierarchy-0001.xml",dir,diagnostics);
        require("ok".equals(result.getString("snapshot")),"complete snapshot failed: "+result.getString("error"));
        childRead("xml",new File(dir,"hierarchy-0001.xml").getPath(),"");
        require("3".equals(result.getString("nodes")),"node count changed");
        require("7".equals(result.getString("child_query_count")) && "49".equals(result.getString("child_query_ms")),"root/export query attribution changed");
        require("4".equals(result.getString("export_child_query_count")) && "28".equals(result.getString("export_child_query_ms")),"export query attribution changed");
        long previous=0;
        for(String phase:new String[]{"export_started","export_serialization_started","export_serialization_finished","export_flush_started","export_flush_finished","export_close_started","export_close_finished","export_finished"}) {
            long at=Long.parseLong(diagnostics.getString("helper_last_"+phase+"_uptime_ms"));
            require(at>=previous,"export diagnostic clocks/order changed"); previous=at;
        }
        require(diagnostics.keySet().size()<25,"unbounded per-node diagnostic records");
        JSONObject response=new JSONObject().put("protocol",1).put("request_id","request").put("filename","hierarchy-0001.xml").put("code",-1);
        writeJson(dir,"response.json",response); childRead("json",new File(dir,"response.json").getPath(),response.toString());
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
        h.automation.root=tree(); h.automation.root.throwChild=true; h.automation.rootDelay=3;
        Bundle queryFailure=h.snapshot(h.automation,"hierarchy-0008.xml",dir,new Bundle());
        require("failed".equals(queryFailure.getString("snapshot")) && "1".equals(queryFailure.getString("child_query_count")) && "7".equals(queryFailure.getString("child_query_ms")),"throwing query attribution/error lost");
        h.arguments.putString("session_nonce","test-session"); h.onStart();
        require(h.finishCode==-1 && "finished".equals(h.finished.getString("session")) && "failed".equals(h.finished.getString("helper_last_snapshot_status")),"failed snapshot changed normal session close");
        require("1".equals(h.finished.getString("helper_last_snapshot_child_query_count")) &&
                "7".equals(h.finished.getString("helper_last_snapshot_child_query_ms")) &&
                h.finished.getString("helper_last_snapshot_export_child_query_count")==null,
                "final failed-request query diagnostics missing or mixed with previous export");
        for(String value:h.finished.values.values()) require(value.length()<=1024,"unbounded final diagnostic string");
        JSONObject closed=new JSONObject().put("state","closed");
        writeJson(dir,"closed.json",closed); childRead("json",new File(dir,"closed.json").getPath(),closed.toString());
        h.failSession=true; h.onStart(); require(h.finishCode==0 && "failed".equals(h.finished.getString("snapshot")),"real session failure changed close code");
        require(FileOutputStream.syncCalls==0,"ephemeral publication forced durability");
        System.out.println("Passed production Java cross-process publication, export failures, deadlines and diagnostics");
    }
''' + methods + '\n}\n'
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            file = directory / 'NativeSnapshotPublicationHarness.java'
            file.write_text(harness)
            compiled = subprocess.run([java, '--module', 'jdk.compiler/com.sun.tools.javac.Main',
                                       '-d', str(directory), str(file)], capture_output=True, timeout=30)
            self.assertEqual(0, compiled.returncode, compiled.stderr.decode())
            exercised = subprocess.run([java, '-cp', str(directory), 'NativeSnapshotPublicationHarness',
                                        'exercise', str(directory / 'session')],
                                       capture_output=True, timeout=30)
            self.assertEqual(0, exercised.returncode, exercised.stderr.decode())
            self.assertIn('Passed production Java cross-process publication, export failures, deadlines and diagnostics',
                          exercised.stdout.decode())


if __name__ == '__main__':
    unittest.main()
