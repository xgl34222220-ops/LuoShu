#!/usr/bin/env python3
"""One 15-second public Perfetto cold-start diagnostic, never acceptance or delivery."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import startup_gpu_probe as base

ROOT = Path(__file__).resolve().parents[1]
JAVA = ROOT/'android-app/app/src/main/java/io/github/xgl34222220/luoshu'
PACKAGE = base.PACKAGE
HELPER = '''package io.github.xgl34222220.luoshu

import android.os.Build
import android.os.Trace
import java.util.concurrent.atomic.AtomicInteger

internal object StartupTrace {
    private val sequence = AtomicInteger()
    fun begin(name: String): Int {
        val cookie = sequence.incrementAndGet()
        if (Build.VERSION.SDK_INT >= 29) Trace.beginAsyncSection("LuoShuDiag:$name", cookie)
        return cookie
    }
    fun end(name: String, cookie: Int) {
        if (Build.VERSION.SDK_INT >= 29) Trace.endAsyncSection("LuoShuDiag:$name", cookie)
    }
    fun <T> sync(name: String, block: () -> T): T {
        Trace.beginSection("LuoShuDiag:$name")
        try { return block() } finally { Trace.endSection() }
    }
    suspend fun <T> async(name: String, block: suspend () -> T): T {
        val cookie = begin(name)
        try { return block() } finally { end(name, cookie) }
    }
}
'''
CONFIG = '''duration_ms: 15000
buffers { size_kb: 65536 fill_policy: DISCARD }
data_sources { config {
  name: "linux.ftrace"
  ftrace_config {
    ftrace_events: "sched/sched_switch"
    ftrace_events: "sched/sched_waking"
    ftrace_events: "sched/sched_process_exit"
    ftrace_events: "task/task_newtask"
    ftrace_events: "task/task_rename"
    ftrace_events: "power/cpu_frequency"
    ftrace_events: "power/cpu_idle"
    atrace_categories: "gfx"
    atrace_categories: "view"
    atrace_categories: "am"
    atrace_categories: "wm"
    atrace_categories: "dalvik"
    atrace_categories: "binder_driver"
    atrace_apps: "io.github.xgl34222220.luoshu.debug"
  }
} }
data_sources { config {
  name: "linux.process_stats"
  process_stats_config { scan_all_processes_on_start: true proc_stats_poll_ms: 250 }
} }
data_sources { config {
  name: "android.surfaceflinger.frametimeline"
} }
data_sources { config {
  name: "linux.perf"
  perf_event_config {
    timebase { counter: SW_CPU_CLOCK frequency: 99 timestamp_clock: PERF_CLOCK_MONOTONIC }
    callstack_sampling {
      scope { target_cmdline: "io.github.xgl34222220.luoshu.debug" }
      kernel_frames: false
    }
  }
} }
'''
QUERIES = {
 'diagnostic-markers': "SELECT id,ts,dur,name,track_id FROM slice WHERE name GLOB 'LuoShuDiag:*' ORDER BY ts;",
 'render-main-slices': "SELECT s.id,s.ts,s.dur,s.depth,s.parent_id,t.tid,t.name AS thread,s.name FROM slice s JOIN thread_track tt ON tt.id=s.track_id JOIN thread t ON t.utid=tt.utid JOIN process p ON p.upid=t.upid WHERE p.name='io.github.xgl34222220.luoshu.debug' AND (t.name='RenderThread' OR t.is_main_thread=1) ORDER BY s.ts LIMIT 30000;",
 'thread-states': "SELECT st.ts,st.dur,st.state,st.io_wait,st.blocked_function,t.tid,t.name FROM thread_state st JOIN thread t ON t.utid=st.utid JOIN process p ON p.upid=t.upid WHERE p.name='io.github.xgl34222220.luoshu.debug' AND (t.name='RenderThread' OR t.is_main_thread=1) ORDER BY st.ts LIMIT 30000;",
 'sample-leaves': "SELECT t.name AS thread,f.name AS function,m.name AS mapping,COUNT(*) AS samples FROM perf_sample ps JOIN thread t ON t.utid=ps.utid JOIN process p ON p.upid=t.upid JOIN stack_profile_callsite c ON c.id=ps.callsite_id JOIN stack_profile_frame f ON f.id=c.frame_id JOIN stack_profile_mapping m ON m.id=f.mapping WHERE p.name='io.github.xgl34222220.luoshu.debug' GROUP BY t.name,f.name,m.name ORDER BY samples DESC LIMIT 150;",
 'samples': "SELECT ps.ts,t.tid,t.name,ps.callsite_id,ps.unwind_error FROM perf_sample ps JOIN thread t ON t.utid=ps.utid JOIN process p ON p.upid=t.upid WHERE p.name='io.github.xgl34222220.luoshu.debug' ORDER BY ps.ts LIMIT 30000;",
 'quality': "SELECT name,idx,value,severity,source FROM stats WHERE value!=0 ORDER BY severity,name;",
}


def transform(name, s):
    one = base.replace_once
    if name == 'LuoShuApplication.kt':
        for marker,label in [('googleFontMaintenance.register()','Application.register'),
            ('NativeImportNotificationController.ensureChannel(this)','Application.channel'),
            ('superviseNativeImport()','Application.importSupervisor')]:
            s=one(s,'        '+marker,'        StartupTrace.sync("'+label+'") { '+marker+' }')
    elif name == 'LuoShuAppShell.kt':
        s=one(s,'        viewModel.refresh()','        StartupTrace.sync("refresh_request") { viewModel.refresh() }')
    elif name == 'LuoShuViewModel.kt':
        s=one(s,'refreshJob = viewModelScope.launch {\n            try {',
            'refreshJob = viewModelScope.launch {\n            val traceCookie = StartupTrace.begin("refresh_coroutine")\n            try {')
        s=one(s,'                initialStatusReady.value = true',
            '                initialStatusReady.value = true\n                StartupTrace.end("refresh_coroutine", traceCookie)')
        for call,label in [('fontIndexStore.load()','font_index_load'),('moduleSnapshotStore.load()','module_snapshot_load')]:
            s=one(s,call,'StartupTrace.sync("'+label+'") { '+call+' }')
    elif name == 'RootShell.kt':
        s=one(s,'            executeScopedRequest(command, timeoutMs)',
            '            StartupTrace.async("RootShell.executeScopedRequest") { executeScopedRequest(command, timeoutMs) }')
    elif name == 'NativeImportViewModel.kt':
        marker='withContext(Dispatchers.IO) { queueStore.load() }'
        if s.count(marker)<1: raise RuntimeError('Queue-load source changed')
        s=s.replace(marker,'withContext(Dispatchers.IO) { StartupTrace.sync("import_queue_load") { queueStore.load() } }')
    elif name == 'MainActivity.kt':
        s=one(s,'        firstContentDrawn = true',
            '        StartupTrace.sync("first_frame_delivered") { Unit }\n        firstContentDrawn = true')
    return s


def setup(out):
    if (JAVA/'StartupTrace.kt').exists(): raise RuntimeError('Trace preparation is once only')
    base.PROBE=base.replace_once(base.PROBE,'                metric("total_ns", FrameMetrics.TOTAL_DURATION)',
        '                metric("intended_vsync_ns", FrameMetrics.INTENDED_VSYNC_TIMESTAMP)\n'
        '                metric("vsync_ns", FrameMetrics.VSYNC_TIMESTAMP)\n'
        '                if (Build.VERSION.SDK_INT >= 36) metric("vsync_id", FrameMetrics.FRAME_TIMELINE_VSYNC_ID)\n'
        '                metric("total_ns", FrameMetrics.TOTAL_DURATION)')
    base.prepare('baseline',out)
    changed=[]
    for name in ('LuoShuApplication.kt','LuoShuAppShell.kt','LuoShuViewModel.kt','RootShell.kt','NativeImportViewModel.kt','MainActivity.kt'):
        path=JAVA/name;before=path.read_text();after=transform(name,before)
        if after==before:raise RuntimeError('Missing diagnostic transformation '+name)
        path.write_text(after)
        changed.append({'path':name,'before':hashlib.sha256(before.encode()).hexdigest(),'after':hashlib.sha256(after.encode()).hexdigest()})
    (JAVA/'StartupTrace.kt').write_text(HELPER)
    manifest=ROOT/'android-app/app/src/main/AndroidManifest.xml'
    manifest.write_text(base.replace_once(manifest.read_text(),'        <activity\n            android:name=".MainActivity"',
        '        <profileable android:shell="true" />\n\n        <activity\n            android:name=".MainActivity"'))
    (out/'config.pbtxt').write_text(CONFIG)
    (out/'trace-instrumentation.json').write_text(json.dumps({'role':'diagnostic-only','changed':changed,
        'profileable':'Temporary diagnostic APK only; public shell profiling; not added to production.',
        'duration_ms':15000,'sampling_hz':99,'cross_coroutine_spans':'Trace.beginAsyncSection/endAsyncSection'},indent=2))
    (out/'temporary-source.diff').write_bytes(subprocess.check_output(['git','diff','--','android-app'],cwd=ROOT))


def record(apk,out):
    index=0
    def adb(*args,timeout=20,check=True):
        nonlocal index
        index+=1;r=subprocess.run(['adb','-s','emulator-5554',*args],capture_output=True,timeout=timeout)
        (out/f'command-{index:02d}.stdout').write_bytes(r.stdout);(out/f'command-{index:02d}.stderr').write_bytes(r.stderr)
        with (out/'commands.jsonl').open('a') as f:f.write(json.dumps({'index':index,'args':args,'returncode':r.returncode})+'\n')
        if check and r.returncode:raise RuntimeError(f'Public command failed {args}: rc={r.returncode}')
        return r
    result={'role':'trace-diagnostic-not-acceptance','launches':0,'errors':[], 'host_load_before':os.getloadavg()}
    try:
        (out/'perfetto-version.txt').write_bytes(adb('shell','perfetto','--version').stdout)
        (out/'data-sources.txt').write_bytes(adb('shell','perfetto','--query').stdout)
        (out/'atrace-categories.txt').write_bytes(adb('shell','atrace','--list_categories').stdout)
        adb('install','-r','-g',str(apk),timeout=120);adb('shell','pm','clear',PACKAGE)
        adb('shell','pm','grant',PACKAGE,'android.permission.POST_NOTIFICATIONS')
        adb('shell','input','keyevent','KEYCODE_WAKEUP');adb('shell','wm','dismiss-keyguard')
        adb('shell','cmd','uimode','night','no');adb('shell','input','keyevent','KEYCODE_HOME')
        time.sleep(20);adb('shell','am','force-stop',PACKAGE)
        if adb('shell','pidof',PACKAGE,check=False).stdout.strip():raise RuntimeError('App PID exists before cold launch')
        adb('push',str(out/'config.pbtxt'),'/data/local/tmp/luoshu-firstframe.pbtxt')
        adb('logcat','-c')
        started=time.monotonic()
        r=adb('shell','perfetto','--background-wait','--txt','-c','/data/local/tmp/luoshu-firstframe.pbtxt',
            '-o','/data/misc/perfetto-traces/luoshu-firstframe.pftrace',timeout=20)
        result['trace_start_stdout']=r.stdout.decode(errors='replace')
        pid_text=result['trace_start_stdout'].strip()
        if not pid_text.isdigit():raise RuntimeError('Cannot verify background trace PID')
        result['trace_pid']=int(pid_text)
        time.sleep(2)
        result['launches']=1;result['host_load_at_launch']=os.getloadavg()
        r=adb('shell','am','start','-W','-n',PACKAGE+'/io.github.xgl34222220.luoshu.MainActivity',timeout=45)
        (out/'launch.txt').write_bytes(r.stdout+r.stderr)
        if b'LaunchState: COLD' not in r.stdout:raise RuntimeError('Not COLD')
        time.sleep(max(0,18-(time.monotonic()-started)))
        # The duration is fixed in the config. Only wait for the verified public
        # client to exit and close its trace file; never terminate or extend it.
        adb('shell',f'while [ -d /proc/{result["trace_pid"]} ]; do sleep 0.1; done',timeout=8)
        adb('pull','/data/misc/perfetto-traces/luoshu-firstframe.pftrace',str(out/'firstframe.pftrace'),timeout=30)
        trace=out/'firstframe.pftrace'
        if not trace.is_file() or trace.stat().st_size<256:raise RuntimeError('Trace missing or empty')
        result['trace_bytes']=trace.stat().st_size;result['trace_sha256']=hashlib.sha256(trace.read_bytes()).hexdigest()
        logs=adb('logcat','-d','-v','threadtime',timeout=30).stdout;(out/'logcat.txt').write_bytes(logs)
        (out/'gfxinfo.txt').write_bytes(adb('shell','dumpsys','gfxinfo',PACKAGE,'framestats',timeout=30).stdout)
        (out/'properties.txt').write_bytes(adb('shell','getprop').stdout)
        result['metrics']=[json.loads(l.split('LuoShuGpuDiag:',1)[1].strip()) for l in logs.decode(errors='replace').splitlines() if 'LuoShuGpuDiag:' in l]
        result['collection_complete']=True
        result['attribution']='Unknown until trace sources, samples, symbols and captured interval are validated.'
    except Exception as e:
        result['errors'].append(f'{type(e).__name__}: {e}');result['blocked']=True
        raise
    finally:
        result['host_load_after']=os.getloadavg();(out/'result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))


def analyze(tool,out):
    results=[]
    for name,sql in QUERIES.items():
        q=out/(name+'.sql');q.write_text(sql)
        r=subprocess.run([str(tool),'query','-f',str(q),str(out/'firstframe.pftrace')],capture_output=True,timeout=90)
        (out/(name+'.csv')).write_bytes(r.stdout);(out/(name+'.stderr')).write_bytes(r.stderr)
        results.append({'query':name,'returncode':r.returncode,'stdout_bytes':len(r.stdout)})
    (out/'analysis-status.json').write_text(json.dumps(results,indent=2));print(json.dumps(results,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('setup','record','analyze'))
    p.add_argument('--apk',type=Path);p.add_argument('--processor',type=Path)
    p.add_argument('--output',type=Path,default=ROOT/'trace-output');a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    if a.action=='setup':setup(a.output)
    elif a.action=='record':
        if a.apk is None:p.error('--apk required')
        record(a.apk.resolve(),a.output)
    else:
        if a.processor is None:p.error('--processor required')
        analyze(a.processor.resolve(),a.output)
