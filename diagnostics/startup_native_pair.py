#!/usr/bin/env python3
"""One paired diagnostic; two fresh AVDs, no production change or deliverable APK."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from startup_gpu_probe import PROBE, PACKAGE, prepare

ROOT = Path(__file__).resolve().parents[1]
NATIVE_ACTIVITY = '''package io.github.xgl34222220.luoshu

import android.app.Activity
import android.graphics.drawable.ColorDrawable
import android.os.Build
import android.os.Bundle
import android.view.Gravity
import android.widget.TextView

class MainActivity : Activity() {
    override fun onCreate(state: Bundle?) {
        setTheme(R.style.Theme_LuoShuHybrid)
        super.onCreate(state)
        StartupGpuProbe.install(window)
        if (Build.VERSION.SDK_INT >= 30) window.setDecorFitsSystemWindows(false)
        val color = resources.getColor(R.color.launch_background, theme)
        window.setBackgroundDrawable(ColorDrawable(color))
        setContentView(TextView(this).apply {
            text = "Native diagnostic control"
            textSize = 20f
            gravity = Gravity.CENTER
            setTextColor(0xff202020.toInt())
            setBackgroundColor(color)
        })
    }
}
'''
NATIVE_MANIFEST = '''<manifest xmlns:android="http://schemas.android.com/apk/res/android">
    <uses-permission android:name="android.permission.POST_NOTIFICATIONS"/>
    <application android:theme="@style/Theme.LuoShuHybrid" android:label="Native diagnostic control"
        android:allowBackup="false" android:hardwareAccelerated="true">
        <activity android:name=".MainActivity" android:theme="@style/Theme.LuoShuLaunch" android:exported="true">
            <intent-filter><action android:name="android.intent.action.MAIN"/>
                <category android:name="android.intent.category.LAUNCHER"/></intent-filter>
        </activity>
    </application>
</manifest>'''
NATIVE_GRADLE = '''plugins { id("com.android.application") }
android {
    namespace = "io.github.xgl34222220.luoshu"
    compileSdk = 37
    defaultConfig {
        applicationId = "io.github.xgl34222220.luoshu"
        minSdk = 28
        targetSdk = 36
        versionCode = 1
        versionName = "diagnostic-only"
    }
    buildTypes {
        getByName("debug") {
            applicationIdSuffix = ".debug"
            isDebuggable = false
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"))
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}
'''


def setup(native, output):
    if native.exists():
        raise RuntimeError('Native control project already exists; no repeat preparation')
    prepare('baseline', output / 'app')
    source = ROOT / 'android-app'
    native.mkdir(parents=True)
    for name in ('settings.gradle.kts', 'build.gradle.kts', 'gradle.properties'):
        if (source/name).is_file(): shutil.copy2(source/name, native/name)
    main = native/'app/src/main'
    main.mkdir(parents=True)
    shutil.copytree(source/'app/src/main/res', main/'res')
    java = main/'java/io/github/xgl34222220/luoshu'
    java.mkdir(parents=True)
    (java/'MainActivity.kt').write_text(NATIVE_ACTIVITY)
    (java/'StartupGpuProbe.kt').write_text(PROBE)
    (main/'AndroidManifest.xml').write_text(NATIVE_MANIFEST)
    (native/'app/build.gradle.kts').write_text(NATIVE_GRADLE)
    assert not any(p.name == 'LuoShuApplication.kt' for p in native.rglob('*.kt'))
    report = {'role': 'diagnostic-only', 'order': ['app', 'native'],
              'same_instrumentation_sha256': hashlib.sha256(PROBE.encode()).hexdigest(),
              'native_kotlin_sources': sorted(str(p.relative_to(native)) for p in native.rglob('*.kt')),
              'native_dependencies': 'No Compose, AndroidX, custom Application, Root or font subsystem',
              'limitations': 'One fixed-order pair; guest AVD data and processes are fresh, host caches/load are not reset.'}
    (output/'pair-manifest.json').write_text(json.dumps(report, indent=2))
    (output/'native-project.gradle.kts').write_text(NATIVE_GRADLE)
    (output/'native-manifest.xml').write_text(NATIVE_MANIFEST)


def analyze_video(path, out):
    import numpy as np
    probe = subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-show_entries',
        'stream=width,height,time_base:frame=pts,pts_time','-of','json',str(path)],capture_output=True,timeout=20,check=True)
    (out/'video-probe.json').write_bytes(probe.stdout)
    info = json.loads(probe.stdout); stream = info['streams'][0]; frames = info['frames']
    if not frames or any('pts' not in f or 'pts_time' not in f for f in frames):
        raise RuntimeError('Missing original video PTS')
    if any(int(b['pts']) <= int(a['pts']) for a,b in zip(frames,frames[1:])):
        raise RuntimeError('Original PTS not strictly increasing')
    w,h = stream['width'],stream['height']
    proc = subprocess.Popen(['ffmpeg','-v','error','-i',str(path),'-map','0:v:0','-fps_mode','passthrough',
        '-f','rawvideo','-pix_fmt','rgb24','pipe:1'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    records=[]
    try:
        while True:
            raw = proc.stdout.read(w*h*3)
            if not raw: break
            if len(raw)!=w*h*3 or len(records)>=len(frames):
                raise RuntimeError('Video frame byte/count mismatch')
            a=np.frombuffer(raw,dtype=np.uint8).reshape(h,w,3)
            interior=a[int(h*.06):int(h*.94),int(w*.04):int(w*.96)]
            black=float(np.mean(interior.max(axis=2)<8))
            record={'frame':len(records), 'pts':frames[len(records)]['pts'],
                    'pts_time':frames[len(records)]['pts_time'], 'black_fraction':black,
                    'rgb_sha256':hashlib.sha256(raw).hexdigest()}
            records.append(record)
        stderr=proc.stderr.read(); code=proc.wait(timeout=15)
        (out/'video-decode.stderr').write_bytes(stderr)
        if code or len(records)!=len(frames): raise RuntimeError('Incomplete original-frame decode')
    finally:
        if proc.poll() is None: proc.kill();proc.wait()
    (out/'all-frames.json').write_text(json.dumps(records,indent=2))
    return {'sha256':hashlib.sha256(path.read_bytes()).hexdigest(), 'frame_count':len(records),
            'original_pts_complete':True,'black_frames':[r for r in records if r['black_fraction']>=.995],
            'scope':'Full-frame decode and unchanged black threshold only; not startup visual acceptance.'}


def run_case(case, apk, out):
    index=0
    def adb(*args,timeout=20,check=True):
        nonlocal index
        index+=1
        r=subprocess.run(['adb','-s','emulator-5554',*args],capture_output=True,timeout=timeout)
        (out/f'command-{index:02d}.stdout').write_bytes(r.stdout)
        (out/f'command-{index:02d}.stderr').write_bytes(r.stderr)
        with (out/'commands.jsonl').open('a') as f:f.write(json.dumps({'index':index,'args':args,'returncode':r.returncode})+'\n')
        if check and r.returncode:raise RuntimeError(f'ADB command failed: {args}, rc={r.returncode}')
        return r
    result={'role':'paired-diagnostic-not-acceptance','case':case,'order':1 if case=='app' else 2,
            'app_launches':0,'host_load_before':os.getloadavg(),'host_cpu_count':os.cpu_count(),'metrics':[], 'errors':[]}
    recorder=None
    try:
        result['apk_sha256']=hashlib.sha256(apk.read_bytes()).hexdigest()
        adb('install','-r','-g',str(apk),timeout=120)
        adb('shell','pm','clear',PACKAGE)
        adb('shell','pm','grant',PACKAGE,'android.permission.POST_NOTIFICATIONS')
        adb('shell','input','keyevent','KEYCODE_WAKEUP')
        adb('shell','wm','dismiss-keyguard')
        adb('shell','cmd','uimode','night','no')
        adb('shell','input','keyevent','KEYCODE_HOME')
        time.sleep(20)
        adb('shell','am','force-stop',PACKAGE)
        if adb('shell','pidof',PACKAGE,check=False).stdout.strip():raise RuntimeError('PID present before cold launch')
        adb('logcat','-c')
        adb('shell','dumpsys','gfxinfo',PACKAGE,'reset',check=False)
        remote='/sdcard/paired-diagnostic.mp4'
        recorder=subprocess.Popen(['adb','-s','emulator-5554','shell','screenrecord','--time-limit','30',
            '--bit-rate','2000000','--size','720x1560',remote],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        time.sleep(.2)
        if recorder.poll() is not None:raise RuntimeError('Recorder exited before launch')
        result['app_launches']=1
        result['host_load_at_launch']=os.getloadavg()
        r=adb('shell','am','start','-W','-n',PACKAGE+'/io.github.xgl34222220.luoshu.MainActivity',timeout=45)
        (out/'launch.txt').write_bytes(r.stdout+r.stderr)
        if b'LaunchState: COLD' not in r.stdout:raise RuntimeError('System did not report COLD')
        stdout,stderr=recorder.communicate(timeout=35)
        (out/'recorder.stdout').write_bytes(stdout);(out/'recorder.stderr').write_bytes(stderr)
        if recorder.returncode:raise RuntimeError('Recorder failed')
        adb('pull',remote,str(out/'original.mp4'),timeout=30)
        logs=adb('logcat','-d','-v','threadtime',timeout=30).stdout
        (out/'logcat.txt').write_bytes(logs)
        for name,args in [('gfxinfo',('dumpsys','gfxinfo',PACKAGE,'framestats')),
                          ('surfaceflinger',('dumpsys','SurfaceFlinger')),('properties',('getprop',)),
                          ('window',('dumpsys','window'))]:
            (out/(name+'.txt')).write_bytes(adb('shell',*args,timeout=30).stdout)
        for line in logs.decode(errors='replace').splitlines():
            if 'LuoShuGpuDiag:' in line:result['metrics'].append(json.loads(line.split('LuoShuGpuDiag:',1)[1].strip()))
        first=next((m for m in result['metrics'] if m['first_draw']==1),None)
        if first is None:raise RuntimeError('No first-draw metrics; no timing inferred')
        result['first_frame_metrics']=first
        result['surface_sync_timeouts']=[l for l in logs.decode(errors='replace').splitlines()
            if 'SurfaceSyncGroup' in l and 'Failed to receive transaction' in l]
        result['video']=analyze_video(out/'original.mp4',out)
        result['measurement_complete']=True
    except Exception as error:
        result['errors'].append(f'{type(error).__name__}: {error}')
        raise
    finally:
        if recorder is not None and recorder.poll() is None:recorder.kill();recorder.communicate(timeout=5)
        result['host_load_after']=os.getloadavg()
        (out/'result.json').write_text(json.dumps(result,indent=2))
        print(json.dumps(result,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=('setup','run'))
    p.add_argument('--native-project',type=Path)
    p.add_argument('--case',choices=('app','native'))
    p.add_argument('--apk',type=Path)
    p.add_argument('--output',type=Path,default=ROOT/'paired-output')
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    if a.action=='setup':
        if a.native_project is None:p.error('--native-project required')
        (a.output/'app').mkdir(exist_ok=True);setup(a.native_project,a.output)
    else:
        if a.case is None or a.apk is None:p.error('--case and --apk required')
        run_case(a.case,a.apk.resolve(),a.output)
