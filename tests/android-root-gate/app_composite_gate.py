"""Actual App slot choices and generation; existing composite proof stays shared."""
import json
from hashlib import sha256
from pathlib import Path
import re
import subprocess
import time
import xml.etree.ElementTree as ET

from app_axis_gate import clickable_text_targets
from app_library_gate import PACKAGE, candidate_notification_deny
from adb_ui import dump_ui
from android_ui_smoke import bounds, center, tab_target, crash_reason
from composite_gate import composite_blockers, fields, run as run_composite

ENTRY = 'ACTUAL_APP_GENERATE_AND_APPLY'
SLOTS = {'cjk': '中文基底', 'latin': '英文字形', 'digit': '数字字形'}


def unique_target(tree, text):
    targets = clickable_text_targets(tree, {text})
    if len(targets) != 1:
        raise ValueError('Exactly one enabled App target required: ' + text)
    return targets[0]


def selected_slot(tree, title, name):
    tile = unique_target(tree, title)
    if name not in {n.get('text') for n in tile.iter('node') if n.get('package') == PACKAGE}:
        raise ValueError('Exact selected font is not inside its App slot: ' + title)
    return tile


def app_composite_blockers(report):
    errors = composite_blockers(report, ENTRY)
    try:
        ui = report.get('ui', {})
        sources = report.get('sources', {})
        selected = ui.get('selected', {})
        if (ui.get('result') != 'PASS' or ui.get('package') != PACKAGE
                or ui.get('action') != '生成并应用' or ui.get('target_fatal') is not False
                or ui.get('anr') is not False or not str(ui.get('pid', '')).isdigit()
                or ui.get('completed_pid') != ui.get('pid')
                or ui.get('admitted_task') != report.get('axes_task', {}).get('task')
                or not ui.get('admitted_task') or not ui.get('old_task') or ui.get('old_task') == ui.get('admitted_task')
                or ui.get('admitted_state', {}).get('task') != ui.get('admitted_task')
                or any(ui.get('admitted_state', {}).get(k) != sources.get(k) for k in SLOTS)
                or ui.get('boot_id') != report.get('reboot', {}).get('before')
                or set(selected) != set(SLOTS)
                or any(selected[k].get('id') != sources.get(k) or not selected[k].get('name')
                       or not selected[k].get('frame') for k in SLOTS)
                or not ui.get('action_frame') or not ui.get('completed_frame')
                or ui.get('completed_screenshot') != 'completed.png'
                or not ui.get('completed_message')
                or ui.get('completed_message') != report.get('task', {}).get('data', {}).get('message')):
            errors.append('actual App composite choices/admission/completion identity incomplete')
        if any(report.get('axes_task', {}).get(k + 'Axes') != 'wght=400' for k in SLOTS):
            errors.append('App composite selected axes differ from intended fixture weights')
    except (TypeError, AttributeError, KeyError, ValueError):
        errors.append('malformed actual App composite UI evidence')
    return errors


def verify_ui_artifact(report, read_bytes):
    """Recompute chosen slot and action assertions from preserved raw XML."""
    errors = []
    try:
        ui = report['ui']
        names = [ui['action_frame'], ui['completed_frame']] + [ui['selected'][k]['frame'] for k in SLOTS]
        if any(not re.fullmatch(r'frame-[0-9]{3}\.xml', name) for name in names):
            raise ValueError('Only owned App composite frames are admissible')
        for slot, title in SLOTS.items():
            choice = ui['selected'][slot]
            selected_slot(ET.fromstring(read_bytes(choice['frame'])), title, choice['name'])
        unique_target(ET.fromstring(read_bytes(ui['action_frame'])), '生成并应用')
        tree = ET.fromstring(read_bytes(ui['completed_frame']))
        text = {n.get('text') for n in tree.iter('node') if n.get('package') == PACKAGE}
        if not {'组合字体已生成', ui['completed_message'], '100%'}.issubset(text):
            errors.append('raw App composite completion frame does not match its successful task')
        image = read_bytes('completed.png')
        if len(image) < 100 or not image.startswith(b'\x89PNG\r\n\x1a\n') or sha256(image).hexdigest() != ui.get('completed_screenshot_sha256'):
            errors.append('actual completed App composite screenshot not bound')
        commands = [json.loads(line) for line in read_bytes('commands.jsonl').decode().splitlines()]
        taps = [c for c in commands if c.get('argv', [])[:3] == ['shell','input','tap'] and c.get('exit') == 0]
        pids = [c.get('stdout', '').strip() for c in commands if c.get('argv') == ['shell','pidof',PACKAGE] and c.get('exit') == 0]
        if pids != [ui.get('pid'), ui.get('completed_pid')]:
            errors.append('App composite report PID differs from actual ADB observations')
        if len(taps) < 8 or any(c.get('exit') != 0 or 'mix_start' in ' '.join(c.get('argv', []))
                               or 'font_mix_controller.sh' in ' '.join(c.get('argv', [])) for c in commands):
            errors.append('actual App composite UI commands missing or replaced by CLI admission')
    except (TypeError, AttributeError, KeyError, ValueError, ET.ParseError) as error:
        errors.append('raw App composite UI evidence invalid: ' + str(error))
    return errors


def qualify(report, adb, module, root, command, boot, font_hashes, assert_mounted,
            switch, stock, ids, fonts, output):
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    ui = {'result': 'RUNNING', 'package': PACKAGE, 'selected': {}}
    report['ui'] = ui
    serial = [adb, '-s', 'emulator-5554']
    frames = 0

    def save():
        (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')

    def run(*args, timeout=60):
        result = subprocess.run(serial + list(args), capture_output=True, text=True, timeout=timeout)
        with (output / 'commands.jsonl').open('a') as log:
            log.write(json.dumps(dict(argv=args, exit=result.returncode,
                                      stdout=result.stdout, stderr=result.stderr)) + '\n')
        if result.returncode:
            raise RuntimeError('App composite ADB failed: ' + result.stderr)
        return result.stdout

    def frame():
        nonlocal frames
        raw = dump_ui(serial, '/data/local/tmp/luoshu-app-composite-ui')
        name = f'frame-{frames:03d}.xml'; frames += 1
        (output / name).write_text(raw)
        logs = run('logcat', '-d', '-s', 'LuoShuStartup:I', 'AndroidRuntime:E', 'ActivityManager:I', '*:S')
        (output / 'runtime.log').write_text(logs)
        reason = crash_reason(logs, PACKAGE)
        if reason or "isn't responding" in raw or 'is not responding' in raw:
            raise RuntimeError(reason or 'ANR blocks actual App composite')
        return ET.fromstring(raw), name

    def tap(node):
        x, y = center(node); run('shell', 'input', 'tap', str(x), str(y))

    def scroll(tree, up=False):
        rectangles = [bounds(n) for n in tree.iter('node')
                      if n.get('package') == PACKAGE and n.get('scrollable') == 'true']
        if len(rectangles) != 1:
            raise ValueError('One actual App scroll viewport required')
        left, top, right, bottom = rectangles[0]; x = (left + right) // 2
        first, last = (2,4) if up else (4,2)
        run('shell', 'input', 'swipe', str(x), str(top + (bottom-top)*first//5),
            str(x), str(top + (bottom-top)*last//5), '400')

    def wait_for(select, stage, timeout=90, scroll_missing=False, scroll_up=False):
        ui['stage'] = stage
        deadline = time.monotonic() + timeout
        scrolls = 0; last = 'No matching fresh frame'
        while time.monotonic() < deadline:
            tree, name = frame()
            deny = candidate_notification_deny(tree)
            if deny is not None:
                tap(deny); continue
            try:
                return select(tree), name
            except ValueError as error:
                last = str(error)
                if scroll_missing and scrolls < 12:
                    scroll(tree, up=scroll_up); scrolls += 1
                time.sleep(.4)
        raise RuntimeError('App composite navigation failed at ' + stage + ': ' + last)

    def admit(sources):
        ui['old_task'] = fields(root('cat ' + module + '/config/axes_task.conf', required=False)).get('task')
        ui['boot_id'] = root('cat /proc/sys/kernel/random/boot_id').strip()
        run('shell', 'am', 'force-stop', PACKAGE)
        run('logcat', '-c')
        run('shell', 'am', 'start', '-W', '-n', PACKAGE + '/io.github.xgl34222220.luoshu.MainActivity')
        target, _ = wait_for(lambda t: tab_target(t, '组合', PACKAGE), 'composition-tab')
        tap(target)
        ui['pid'] = run('shell', 'pidof', PACKAGE).strip()
        if not ui['pid'].isdigit():
            raise RuntimeError('One actual App PID required')
        for slot, title in SLOTS.items():
            font, = [f for f in fonts if f.get('id') == sources[slot] and f.get('valid') is True]
            font_name = font['name']
            tile, _ = wait_for(lambda t: unique_target(t, title), slot + '-summary')
            tap(tile)
            def font_row(tree):
                text = {n.get('text') for n in tree.iter('node') if n.get('package') == PACKAGE}
                chooser_title = '选择' + {'cjk':'中文','latin':'英文','digit':'数字'}[slot] + '字体'
                if chooser_title not in text:
                    raise ValueError('Exact slot picker title absent')
                return unique_target(tree, font_name)
            row, _ = wait_for(font_row, slot + '-exact-picker-row')
            tap(row)
            _, selected_frame = wait_for(lambda t: selected_slot(t, title, font_name), slot + '-selected')
            ui['selected'][slot] = dict(id=sources[slot], name=font_name, frame=selected_frame)
        action, ui['action_frame'] = wait_for(lambda t: unique_target(t, '生成并应用'),
                                             'generate-and-apply', scroll_missing=True)
        tap(action); ui['action'] = '生成并应用'
        # No CLI mix_start/finalize is used to rescue App admission. Only the
        # newly persisted matching parent can enter the shared completion gate.
        deadline = time.monotonic() + 75
        while time.monotonic() < deadline:
            state = fields(root('cat ' + module + '/config/axes_task.conf', required=False))
            task = state.get('task')
            if task and task != ui['old_task'] and all(state.get(k) == v for k,v in sources.items()):
                if root('cat /proc/sys/kernel/random/boot_id').strip() != ui['boot_id']:
                    raise RuntimeError('Kernel boot changed during actual App admission')
                ui['admitted_task'] = task
                ui['admitted_state'] = state
                save()
                return {'status': 'ok', 'data': {'task': task},
                        'origin': 'NEW_PERSISTED_TASK_AFTER_ACTUAL_APP_TAP'}
            time.sleep(.5)
        raise RuntimeError('Actual App tap did not admit one new matching composite task')

    def prepared():
        def completed(tree):
            text = {n.get('text') for n in tree.iter('node') if n.get('package') == PACKAGE}
            message = report['task']['data']['message']
            if not {'组合字体已生成', message, '100%'}.issubset(text):
                raise ValueError('Actual App successful completion is not visible')
            return tree
        _, ui['completed_frame'] = wait_for(completed, 'actual-App-completed', scroll_missing=True, scroll_up=True)
        ui['completed_message'] = report['task']['data']['message']
        ui['completed_pid'] = run('shell', 'pidof', PACKAGE).strip()
        image = subprocess.run(serial + ['exec-out','screencap','-p'], capture_output=True, timeout=30)
        if image.returncode or not image.stdout.startswith(b'\x89PNG\r\n\x1a\n'):
            raise RuntimeError('Actual completed App composite screenshot absent')
        (output / 'completed.png').write_bytes(image.stdout)
        ui.update(result='PASS', completed_screenshot='completed.png',
                  completed_screenshot_sha256=sha256(image.stdout).hexdigest(), target_fatal=False, anr=False)
        save()

    try:
        run_composite(report, module, root, command, boot, font_hashes, assert_mounted,
                      switch, stock, ids, output, app_admit=admit, app_prepared=prepared)
        report['blockers'] = app_composite_blockers(report)
        if report['blockers']:
            raise RuntimeError('; '.join(report['blockers']))
    except Exception as error:
        report.update(result='FAIL', error=str(error)); ui['result'] = 'FAIL'
        raise
    finally:
        save()
