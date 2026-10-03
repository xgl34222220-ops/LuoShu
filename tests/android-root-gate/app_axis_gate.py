"""Select an original variable fixture in the real App; never apply/mount it."""
import json
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from android_ui_smoke import bounds, center, tab_target, crash_reason
from adb_ui import dump_ui
from app_library_gate import candidate_notification_deny, PACKAGE


def clickable_text_targets(tree, texts):
    parents = {child: parent for parent in tree.iter() for child in parent}
    targets = []
    for node in tree.iter('node'):
        if node.get('package') != PACKAGE or node.get('text') not in texts:
            continue
        while node is not None:
            if node.get('package') == PACKAGE and node.get('clickable') == 'true' and node.get('enabled') == 'true':
                try:
                    center(node)
                except ValueError:
                    break
                if node not in targets:
                    targets.append(node)
                break
            node = parents.get(node)
    return targets


def slot_chooser(tree, title, font_names):
    headings = [n for n in tree.iter('node') if n.get('package') == PACKAGE and n.get('text') == title]
    if len(headings) != 1:
        raise ValueError('Exact App slot heading is not visible: ' + title)
    targets = clickable_text_targets(tree, set(font_names) | {'点此选择字体'})
    top = center(headings[0])[1]
    following = []
    for node in tree.iter('node'):
        if node.get('package') == PACKAGE and node.get('text') in ('英文字形', '数字字形'):
            try:
                y = center(node)[1]
                if y > top:
                    following.append(y)
            except ValueError:
                pass
    bottom = min(following) if following else float('inf')
    # Compose can flatten a non-clickable card's accessibility hierarchy.
    # Bind the choice to the exact heading's vertical region instead of
    # guessing a parent container or tapping a similarly named later slot.
    choices = [target for target in targets if top < center(target)[1] < bottom]
    if len(choices) != 1:
        raise ValueError('One exact font chooser is required within the CJK region')
    return choices[0], (top, bottom)


def region_texts(tree, region):
    texts = set()
    for node in tree.iter('node'):
        if node.get('package') == PACKAGE:
            try:
                if region[0] <= center(node)[1] < region[1]:
                    texts.add(node.get('text', ''))
            except ValueError:
                pass
    return texts


def qualify(adb, output, font_name, font_names):
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    serial = [adb, '-s', 'emulator-5554']
    report = {'result': 'RUNNING', 'font_name': font_name, 'package': PACKAGE,
              'expected_labels': ['字宽', '纹理细节', 'XTRA'], 'hidden_labels': ['内置参数', 'HIDN'], 'frames': []}
    frame_index = 0

    def run(*args, timeout=60):
        result = subprocess.run(serial + list(args), capture_output=True, text=True, timeout=timeout)
        with (output / 'commands.jsonl').open('a') as log:
            log.write(json.dumps({'argv': args, 'exit': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr}) + '\n')
        if result.returncode:
            raise RuntimeError('Axis UI ADB command failed: ' + result.stderr)
        return result.stdout

    def frame():
        nonlocal frame_index
        raw = dump_ui(serial, '/data/local/tmp/luoshu-axis-ui')
        path = output / f'frame-{frame_index:02d}.xml'; path.write_text(raw); frame_index += 1
        logs = run('logcat', '-d', '-s', 'AndroidRuntime:E', 'ActivityManager:I', '*:S')
        (output / 'runtime.log').write_text(logs)
        reason = crash_reason(logs, PACKAGE)
        if reason or "isn't responding" in raw or 'is not responding' in raw:
            raise RuntimeError(reason or 'App ANR blocks actual axis controls')
        tree = ET.fromstring(raw)
        texts = [n.get('text', '') for n in tree.iter('node') if n.get('package') == PACKAGE]
        report['frames'].append({'path': path.name, 'app_texts': texts})
        return tree

    def tap(node):
        x, y = center(node); run('shell', 'input', 'tap', str(x), str(y))

    def wait_for(select, timeout=100):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            tree = frame()
            denied = candidate_notification_deny(tree)
            if denied is not None:
                tap(denied); continue
            try:
                return select(tree)
            except ValueError:
                time.sleep(.4)
        raise RuntimeError('Actual App axis navigation did not converge')

    try:
        run('shell', 'am', 'force-stop', PACKAGE)
        run('logcat', '-c')
        run('shell', 'am', 'start', '-W', '-n', PACKAGE + '/io.github.xgl34222220.luoshu.MainActivity')
        tap(wait_for(lambda tree: tab_target(tree, '组合', PACKAGE)))
        tap(wait_for(lambda tree: slot_chooser(tree, '中文基底', font_names)[0]))

        def fixture_target(tree):
            choices = clickable_text_targets(tree, {font_name})
            if len(choices) != 1:
                raise ValueError('One exact fixture row is required')
            return choices[0]
        tap(wait_for(fixture_target))

        def selected_card(tree):
            _, region = slot_chooser(tree, '中文基底', font_names)
            texts = region_texts(tree, region)
            if font_name not in texts:
                raise ValueError('Selected fixture is not in the actual CJK card yet')
            if any(value in texts for value in report['hidden_labels']):
                raise RuntimeError('A font-internal hidden axis became an ordinary App control')
            if '可变字体' not in texts:
                raise ValueError('Actual variable capability label missing')
            return tree
        tree = wait_for(selected_card, timeout=140)
        scanned = False
        seen = set()
        screenshot = False
        scrolls = 0
        deadline = time.monotonic() + 140
        while time.monotonic() < deadline:
            texts = {n.get('text', '') for n in tree.iter('node') if n.get('package') == PACKAGE}
            seen.update(texts)
            if any(value in texts for value in report['hidden_labels']):
                raise RuntimeError('Hidden axis appeared while scanning the complete CJK card')
            if any(text.startswith('字体轴读取失败：') for text in texts):
                raise RuntimeError('Actual App axis metadata could not be read')
            if '纹理细节' in texts and 'XTRA' in texts and not screenshot:
                image = subprocess.run(serial + ['exec-out', 'screencap', '-p'], capture_output=True, timeout=30)
                if image.returncode or not image.stdout.startswith(b'\x89PNG\r\n\x1a\n'):
                    raise RuntimeError('Actual App axis screenshot absent')
                (output / 'actual-axis-ui.png').write_bytes(image.stdout)
                screenshot = True
            if '英文字形' in texts and all(label in seen for label in report['expected_labels']) and screenshot:
                scanned = True; break
            # When axes are still loading, the next slot may already be visible.
            # Keep that position until the real axis response expands the card.
            if '英文字形' not in texts:
                if scrolls >= 6:
                    raise RuntimeError('Full CJK card did not finish within six overlapping scrolls')
                rectangles = []
                for node in tree.iter('node'):
                    if node.get('package') == PACKAGE:
                        try:
                            rectangles.append(bounds(node))
                        except ValueError:
                            pass
                if not rectangles:
                    raise RuntimeError('Actual App viewport is missing')
                width = max(rect[2] for rect in rectangles); height = max(rect[3] for rect in rectangles)
                run('shell', 'input', 'swipe', str(width // 2), str(int(height * .8)), str(width // 2), str(int(height * .55)), '400')
                scrolls += 1
            else:
                time.sleep(.5)
            tree = frame()
        if not scanned:
            raise RuntimeError('Full CJK axis card was not inspected through the next slot')
        report.update(result='PASS', cjk_card_scanned_to_next_slot=True, hidden_axis_visible=False,
                      target_fatal=False, anr=False, observed_labels=sorted(seen),
                      actual_app_pid=run('shell', 'pidof', PACKAGE).strip())
        if not report['actual_app_pid'].isdigit():
            raise RuntimeError('Actual App exited after axis inspection')
    except Exception as error:
        report.update(result='FAIL', error=str(error))
        raise
    finally:
        (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    return report
