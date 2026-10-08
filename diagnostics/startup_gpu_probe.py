#!/usr/bin/env python3
"""One-shot diagnostic only. Temporary checkout edits; never acceptance or delivery."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
JAVA = ROOT / 'android-app/app/src/main/java/io/github/xgl34222220/luoshu'
MODES = ('baseline', 'flat_backdrop', 'no_glass_pipeline', 'simple_glyphs')
PACKAGE = 'io.github.xgl34222220.luoshu.debug'
PROBE = '''package io.github.xgl34222220.luoshu

import android.os.Build
import android.os.Handler
import android.os.HandlerThread
import android.util.Log
import android.view.FrameMetrics
import android.view.Window
import org.json.JSONObject

// Temporary diagnostic source injected identically into every control APK.
internal object StartupGpuProbe {
    fun install(window: Window) {
        val thread = HandlerThread("LuoShuGpuDiagnostic").apply { start() }
        var count = 0
        window.addOnFrameMetricsAvailableListener({ _, original, dropped ->
            if (count < 20) {
                val frame = FrameMetrics(original)
                val record = JSONObject().put("index", count++)
                    .put("dropped_since_previous", dropped)
                    .put("first_draw", frame.getMetric(FrameMetrics.FIRST_DRAW_FRAME))
                fun metric(name: String, key: Int) {
                    val value = frame.getMetric(key)
                    record.put(name, if (value < 0L) JSONObject.NULL else value)
                }
                metric("total_ns", FrameMetrics.TOTAL_DURATION)
                metric("draw_ns", FrameMetrics.DRAW_DURATION)
                metric("sync_ns", FrameMetrics.SYNC_DURATION)
                metric("command_issue_ns", FrameMetrics.COMMAND_ISSUE_DURATION)
                metric("swap_ns", FrameMetrics.SWAP_BUFFERS_DURATION)
                metric("layout_ns", FrameMetrics.LAYOUT_MEASURE_DURATION)
                metric("unknown_delay_ns", FrameMetrics.UNKNOWN_DELAY_DURATION)
                if (Build.VERSION.SDK_INT >= 31) metric("gpu_ns", FrameMetrics.GPU_DURATION)
                else record.put("gpu_ns", JSONObject.NULL)
                Log.i("LuoShuGpuDiag", record.toString())
            }
        }, Handler(thread.looper))
    }
}
'''


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise RuntimeError(f'Expected exactly one unchanged patch anchor: {old[:80]}')
    return text.replace(old, new, 1)


def variant_source(mode, files):
    """Pure transformation, fail closed on source drift; baseline only adds instrumentation."""
    if mode not in MODES:
        raise ValueError('Unknown diagnostic mode')
    output = dict(files)
    output['MainActivity.kt'] = replace_once(output['MainActivity.kt'],
        '        super.onCreate(savedInstanceState)',
        '        super.onCreate(savedInstanceState)\n        StartupGpuProbe.install(window)')
    if mode == 'flat_backdrop':
        path = 'ui/launch/LuoShuGlassBackdropDrawable.kt'
        output[path] = replace_once(output[path],
            '        layers.forEach { layer -> canvas.drawRect(0f, 0f, bounds.width().toFloat(), bounds.height().toFloat(), layer) }',
            '        canvas.drawColor(if (dark && pureBlack) 0xFF000000.toInt() else\n'
            '            if (dark) LuoShuGlassPalette.DarkBackground else LuoShuGlassPalette.LightBackground)')
    elif mode == 'no_glass_pipeline':
        path = 'LuoShuAppShell.kt'
        output[path] = replace_once(output[path],
            '    val blurActive = firstFrameCommitted && appearance.blurEnabled &&',
            '    val blurActive = false && firstFrameCommitted && appearance.blurEnabled &&')
    elif mode == 'simple_glyphs':
        path = 'ui/theme/LuoShuIconSystem.kt'
        source = replace_once(output[path], 'import androidx.compose.foundation.layout.Box',
            'import androidx.compose.foundation.layout.Box\nimport androidx.compose.foundation.background')
        output[path] = replace_once(source, '''        Icon(
            imageVector = imageVector,
            contentDescription = contentDescription,
            modifier = Modifier.fillMaxSize().scale(opticalScale),
            tint = resolvedTint,
        )''', '''        Box(Modifier.fillMaxSize().scale(opticalScale).background(resolvedTint)
            .semantics { if (contentDescription != null) this.contentDescription = contentDescription })''')
    return output


def prepare(mode, out):
    paths = ('MainActivity.kt', 'LuoShuAppShell.kt',
             'ui/launch/LuoShuGlassBackdropDrawable.kt', 'ui/theme/LuoShuIconSystem.kt')
    originals = {name: (JAVA / name).read_text() for name in paths}
    modified = variant_source(mode, originals)
    probe = JAVA / 'StartupGpuProbe.kt'
    if probe.exists():
        raise RuntimeError('Diagnostic preparation cannot be repeated')
    report = {'role': 'diagnostic-only-not-deliverable', 'mode': mode,
              'sha': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'instrumentation_identical_in_all_modes': True, 'files': []}
    for name, content in modified.items():
        report['files'].append({'path': name,
            'before_sha256': hashlib.sha256(originals[name].encode()).hexdigest(),
            'after_sha256': hashlib.sha256(content.encode()).hexdigest(),
            'changed': content != originals[name]})
        (JAVA / name).write_text(content)
    probe.write_text(PROBE)
    report['probe_sha256'] = hashlib.sha256(PROBE.encode()).hexdigest()
    (out / 'manifest.json').write_text(json.dumps(report, indent=2))
    (out / 'temporary-source.diff').write_bytes(subprocess.check_output(['git', 'diff', '--', 'android-app'], cwd=ROOT))


def run(mode, apk, out):
    command_index = 0
    def adb(*args, timeout=20, check=True):
        nonlocal command_index
        command_index += 1
        result = subprocess.run(['adb', '-s', 'emulator-5554', *args], capture_output=True, timeout=timeout)
        prefix = out / f'command-{command_index:02d}'
        prefix.with_suffix('.stdout').write_bytes(result.stdout)
        prefix.with_suffix('.stderr').write_bytes(result.stderr)
        with (out / 'commands.jsonl').open('a') as stream:
            stream.write(json.dumps({'index': command_index, 'args': args, 'returncode': result.returncode})+'\n')
        if check and result.returncode:
            raise RuntimeError(f'ADB command failed: {args}, rc={result.returncode}')
        return result
    report = {'role': 'diagnostic-only-not-acceptance', 'mode': mode, 'target_app_launches': 0,
              'fresh_avd_required': True, 'metrics': [], 'errors': []}
    report['host_load_before'] = os.getloadavg()
    report['comparison_limit'] = 'One cold sample per variant on separate hosted runners; not statistical proof or acceptance.'
    try:
        report['apk_sha256'] = hashlib.sha256(apk.read_bytes()).hexdigest()
        adb('install', '-r', '-g', str(apk), timeout=120)
        adb('shell', 'pm', 'clear', PACKAGE)
        adb('shell', 'pm', 'grant', PACKAGE, 'android.permission.POST_NOTIFICATIONS')
        adb('shell', 'input', 'keyevent', 'KEYCODE_WAKEUP')
        adb('shell', 'wm', 'dismiss-keyguard')
        adb('shell', 'cmd', 'uimode', 'night', 'no')
        adb('shell', 'input', 'keyevent', 'KEYCODE_HOME')
        # Identical fixed fixture settling; never launches or warms the target App.
        # This is not a readiness/visual acceptance claim and never repeats.
        time.sleep(20)
        adb('shell', 'am', 'force-stop', PACKAGE)
        if adb('shell', 'pidof', PACKAGE, check=False).stdout.strip():
            raise RuntimeError('Target App PID exists before diagnostic cold launch')
        adb('logcat', '-c')
        adb('shell', 'dumpsys', 'gfxinfo', PACKAGE, 'reset', check=False)
        report['target_app_launches'] = 1
        launch = adb('shell', 'am', 'start', '-W', '-n', PACKAGE+'/io.github.xgl34222220.luoshu.MainActivity', timeout=45)
        (out / 'launch.txt').write_bytes(launch.stdout + launch.stderr)
        if b'LaunchState: COLD' not in launch.stdout:
            raise RuntimeError('System did not report a COLD launch')
        time.sleep(12)
        logs = adb('logcat', '-d', '-v', 'threadtime', timeout=30).stdout
        (out / 'logcat.txt').write_bytes(logs)
        (out / 'gfxinfo.txt').write_bytes(adb('shell', 'dumpsys', 'gfxinfo', PACKAGE, 'framestats', timeout=30).stdout)
        (out / 'window.txt').write_bytes(adb('shell', 'dumpsys', 'window', timeout=30).stdout)
        (out / 'system-properties.txt').write_bytes(adb('shell', 'getprop').stdout)
        (out / 'surfaceflinger.txt').write_bytes(adb('shell', 'dumpsys', 'SurfaceFlinger', timeout=30, check=False).stdout)
        for line in logs.decode(errors='replace').splitlines():
            if 'LuoShuGpuDiag:' in line:
                report['metrics'].append(json.loads(line.split('LuoShuGpuDiag:', 1)[1].strip()))
        if not report['metrics'] or not any(x['first_draw'] == 1 for x in report['metrics']):
            raise RuntimeError('Missing first-draw FrameMetrics; no substitute timing inferred')
        report['first_frame_metrics'] = next(x for x in report['metrics'] if x['first_draw'] == 1)
        report['gpu_metric_supported'] = report['first_frame_metrics'].get('gpu_ns') is not None
        report['surface_sync_timeouts'] = [line for line in logs.decode(errors='replace').splitlines()
            if 'SurfaceSyncGroup' in line and 'Failed to receive transaction' in line]
        report['measurement_complete'] = True
    except Exception as error:
        report['errors'].append(f'{type(error).__name__}: {error}')
        raise
    finally:
        report['host_load_after'] = os.getloadavg()
        (out / 'result.json').write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))


def selftest():
    # Anchor/variant isolation only, not an Android performance claim.
    names = ('MainActivity.kt', 'LuoShuAppShell.kt', 'ui/launch/LuoShuGlassBackdropDrawable.kt', 'ui/theme/LuoShuIconSystem.kt')
    files = {name: (JAVA/name).read_text() for name in names}
    expected = {'baseline': set(), 'flat_backdrop': {names[2]},
                'no_glass_pipeline': {names[1]}, 'simple_glyphs': {names[3]}}
    for mode in MODES:
        changed = variant_source(mode, files)
        assert {name for name in files if changed[name] != files[name]} == expected[mode] | {names[0]}
        assert 'StartupGpuProbe.install(window)' in changed[names[0]]
        assert files[names[0]].count('StartupGpuProbe.install(window)') == 0
    try:
        variant_source('invalid', files)
    except ValueError:
        pass
    else:
        raise AssertionError('Unknown mode accepted')
    assert 'JSONObject.NULL' in PROBE and 'count < 20' in PROBE
    print('Four variant-isolation checks and fail-closed mode checks passed; no performance claim.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'run', 'selftest'))
    parser.add_argument('--mode', choices=MODES, default='baseline')
    parser.add_argument('--apk', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT/'diagnostic-output')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.action == 'selftest': selftest()
    elif args.action == 'prepare': prepare(args.mode, args.output)
    else:
        if args.apk is None: parser.error('--apk is required')
        run(args.mode, args.apk.resolve(), args.output)
