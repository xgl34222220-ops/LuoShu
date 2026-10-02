#!/usr/bin/env python3
"""Measure actual .stabletest UI readiness; never inject an App cache or mock root."""
import json
from pathlib import Path
import re
import statistics
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from android_ui_smoke import tab_target, center
from adb_ui import dump_ui

PACKAGE = 'io.github.xgl34222220.luoshu.stabletest'
EVENT = re.compile(r'event=(\w+) elapsed_ms=(\d+)(?: count=(\d+) verified=(true|false))?')


def candidate_notification_deny(tree):
    nodes = list(tree.iter('node'))
    messages = [n.get('text', '') for n in nodes
                if n.get('package') in ('com.google.android.permissioncontroller', 'com.android.permissioncontroller')
                and n.get('resource-id', '').endswith('/permission_message')]
    if messages != ['Allow 洛书·稳定重构测试 to send you notifications?']:
        return None
    buttons = [n for n in nodes if n.get('package') in ('com.google.android.permissioncontroller', 'com.android.permissioncontroller')
               and n.get('resource-id', '').rsplit('/', 1)[-1] in ('permission_deny_button', 'permission_deny_and_dont_ask_again_button')
               and n.get('text') in ("Don't allow", 'Don’t allow') and n.get('enabled') == 'true']
    return buttons[0] if len(buttons) == 1 else None


def measure(adb, output, count):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    samples = []
    def run(*args, timeout=60):
        p = subprocess.run([adb, '-s', 'emulator-5554', *args], capture_output=True, text=True, timeout=timeout)
        with (output / 'commands.jsonl').open('a') as log:
            log.write(json.dumps({'argv': args, 'exit': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr}) + '\n')
        if p.returncode:
            raise RuntimeError('UI ADB failed: ' + p.stderr)
        return p.stdout
    def hierarchy():
        raw = dump_ui([adb, '-s', 'emulator-5554'], '/data/local/tmp/luoshu-library-ui')
        (output / 'last-ui.xml').write_text(raw)
        (output / 'app-runtime.log').write_text(run('logcat', '-d', '-s', 'LuoShuStartup:I', 'AndroidRuntime:E', '*:S'))
        if "isn't responding" in raw or 'is not responding' in raw:
            raise RuntimeError('An ANR dialog blocks actual App library visibility')
        return ET.fromstring(raw)
    def tab(label):
        end = time.monotonic() + 45
        while time.monotonic() < end:
            tree = hierarchy()
            deny = candidate_notification_deny(tree)
            if deny is not None:
                (output / 'notification-declined.xml').write_text(ET.tostring(tree, encoding='unicode'))
                x, y = center(deny)
                run('shell', 'input', 'tap', str(x), str(y))
                time.sleep(.3)
                continue
            try:
                x, y = center(tab_target(tree, label, PACKAGE))
                run('shell', 'input', 'tap', str(x), str(y))
                return
            except ValueError:
                time.sleep(.3)
        raise RuntimeError('Actual App tab not reachable: ' + label)
    def wait_frame(start_event, label):
        pid = run('shell', 'pidof', PACKAGE).strip()
        if not pid.isdigit():
            raise RuntimeError('Expected one actual candidate App process')
        end = time.monotonic() + 180
        while time.monotonic() < end:
            logs = run('logcat', '-d', '--pid=' + pid, '-s', 'LuoShuStartup:I', 'AndroidRuntime:E', '*:S')
            (output / (label + '.log')).write_text(logs)
            if 'FATAL EXCEPTION' in logs and ('Process: ' + PACKAGE) in logs:
                raise RuntimeError('App crashed during library timing')
            events = [m.groups() for m in EVENT.finditer(logs)]
            starts = [int(ms) for event, ms, _, _ in events if event == start_event]
            if starts:
                start = starts[-1]
                ready = [(int(ms), int(n)) for event, ms, n, verified in events
                         if event == 'library_frame' and verified == 'true' and n is not None
                         and int(n) == count and int(ms) >= start]
                if ready:
                    frame, actual = ready[0]
                    visible = hierarchy()
                    if not any(n.get('package') == PACKAGE and n.get('resource-id', '').endswith('luoshu_font_library')
                               for n in visible.iter('node')):
                        raise RuntimeError('Verified frame log exists but actual library UI is not visible')
                    alive = run('shell', 'pidof', PACKAGE).strip()
                    if alive.strip() != pid:
                        raise RuntimeError('App exited after readiness marker')
                    frames = [int(ms) for event, ms, n, verified in events if event == 'library_frame' and int(ms) >= start]
                    first_event = next((int(ms), int(n or 0), verified == 'true') for event, ms, n, verified in events if event == 'library_frame' and int(ms) >= start)
                    inventory_frames = [int(ms) for event, ms, n, verified in events if event == 'library_frame' and n is not None and int(n) == count and int(ms) >= start]
                    opened = [int(ms) for event, ms, _, _ in events if event == 'library_open' and int(ms) >= start]
                    return {'pid': pid, 'first_frame_count': first_event[1], 'first_frame_verified': first_event[2],
                            'first_inventory_frame_ms': min(inventory_frames), 'first_inventory_frame_elapsed_ms': min(inventory_frames) - start,
                            'library_open_to_inventory_first_ms': min(inventory_frames) - opened[-1] if opened else None, 'first_frame_ms': min(frames), 'first_frame_elapsed_ms': min(frames) - start,
                            'library_open_to_verified_ms': frame - opened[-1] if opened else None,
                            'library_open_to_first_ms': min(frames) - opened[-1] if opened else None, 'kind': start_event, 'count': actual, 'verified': True,
                            'start_ms': start, 'frame_ms': frame, 'elapsed_ms': frame - start}
            time.sleep(.5)
        raise RuntimeError('No real verified library frame for expected inventory ' + str(count))
    for repetition in range(3):
        run('shell', 'am', 'force-stop', PACKAGE)
        run('logcat', '-c')
        run('shell', 'am', 'start', '-W', '-n', PACKAGE + '/io.github.xgl34222220.luoshu.MainActivity')
        tab('字体库')
        cold = wait_frame('app_start', f'cold-{repetition}')
        cold['repetition'] = repetition
        cold['note'] = 'Includes real scripted navigation from initial App screen to library'
        samples.append(cold)
        tab('首页')
        home_deadline = time.monotonic() + 30
        while time.monotonic() < home_deadline:
            tree = hierarchy()
            if not any(n.get('resource-id', '').endswith('luoshu_font_library') for n in tree.iter('node')):
                break
            time.sleep(.3)
        else:
            raise RuntimeError('Warm sample did not leave library page')
        run('logcat', '-c')
        tab('字体库')
        warm = wait_frame('library_open', f'warm-{repetition}')
        warm['repetition'] = repetition
        samples.append(warm)
    result = {'result': 'PASS', 'inventory_count': count, 'samples': samples}
    for kind in ('app_start', 'library_open'):
        values = sorted(s['elapsed_ms'] for s in samples if s['kind'] == kind)
        result[kind] = {'median_ms': statistics.median(values), 'p95_ms': values[-1],
                        'samples': len(values), 'p95_method': 'nearest rank; only three samples'}
    (output / 'timing.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


def apply_fixture(adb, font_id, output):
    """Apply one visible synthetic font through the actual App UI, never a CLI substitute."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    def run(*args):
        p = subprocess.run([adb, '-s', 'emulator-5554', *args], capture_output=True, text=True, timeout=60)
        if p.returncode:
            raise RuntimeError('App apply UI command failed: ' + p.stderr)
        return p.stdout
    def snapshot(label):
        raw = dump_ui([adb, '-s', 'emulator-5554'], '/data/local/tmp/luoshu-apply-ui')
        (output / (label + '.xml')).write_text(raw)
        return ET.fromstring(raw)
    tree = snapshot('before-select')
    found = [node for node in tree.iter('node') if node.get('package') == PACKAGE
             and font_id in (node.get('text', '') + node.get('content-desc', ''))]
    if not found:
        raise RuntimeError('Expected synthetic font is not actually visible in App library')
    x, y = center(found[0])
    run('shell', 'input', 'tap', str(x), str(y))
    end = time.monotonic() + 30
    while time.monotonic() < end:
        tree = snapshot('font-details')
        buttons = [node for node in tree.iter('node') if node.get('package') == PACKAGE
                   and node.get('text') == '应用此字体' and node.get('enabled') != 'false']
        if buttons:
            x, y = center(buttons[0])
            run('shell', 'input', 'tap', str(x), str(y))
            confirm_deadline = time.monotonic() + 20
            while time.monotonic() < confirm_deadline:
                confirmation = snapshot('apply-confirmation')
                text = ' '.join(n.get('text', '') for n in confirmation.iter('node'))
                confirms = [n for n in confirmation.iter('node') if n.get('package') == PACKAGE
                            and n.get('text') == '应用' and n.get('enabled') != 'false']
                if font_id in text and '应用字体' in text and confirms:
                    cx, cy = center(confirms[0])
                    run('shell', 'input', 'tap', str(cx), str(cy))
                    snapshot('after-apply-confirmed')
                    return {'font_id': font_id, 'action': 'Actual App detail apply and matching font confirmation tapped',
                            'completion': 'Must be established from a new matching module task and real mounts'}
                time.sleep(.3)
            raise RuntimeError('Matching synthetic-font apply confirmation was not visible')
        scrolls = [n for n in tree.iter('node') if n.get('package') == PACKAGE and n.get('scrollable') == 'true']
        if scrolls:
            bounds = [int(v) for v in re.findall(r'\d+', scrolls[0].get('bounds', ''))]
            if len(bounds) == 4:
                left, top, right, bottom = bounds
                x = (left + right) // 2
                run('shell', 'input', 'swipe', str(x), str(bottom - (bottom-top)//5), str(x), str(top + (bottom-top)//5), '400')
        time.sleep(.3)
    raise RuntimeError('Actual App apply button was not available')
