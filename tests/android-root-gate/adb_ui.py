"""Fresh-only UIAutomator snapshots; Android can return exit 0 on dump errors."""
import subprocess
import time
import xml.etree.ElementTree as ET


def dump_ui(adb, prefix, steps=None, timeout=45):
    steps = steps if steps is not None else []
    end = time.monotonic() + timeout
    last = ''
    while time.monotonic() < end:
        path = prefix + '-' + str(time.monotonic_ns()) + '.xml'
        remaining = max(.1, end - time.monotonic())
        try:
            p = subprocess.run(adb + ['shell', 'uiautomator dump ' + path], capture_output=True, text=True, timeout=min(20, remaining))
        except subprocess.TimeoutExpired:
            steps.append({'ui_dump': path, 'result': 'TIMEOUT'})
            continue
        steps.append({'ui_dump': path, 'exit': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr})
        last = p.stdout + p.stderr
        # An old file is never accepted, even if Android reports exit status 0.
        if p.returncode == 0 and 'dumped to:' in p.stdout and path in p.stdout and 'ERROR:' not in last:
            q = subprocess.run(adb + ['shell', 'cat ' + path], capture_output=True, text=True, timeout=10)
            if q.returncode == 0:
                try:
                    tree = ET.fromstring(q.stdout)
                    if tree.tag != 'hierarchy' or not any(True for _ in tree.iter('node')):
                        raise ET.ParseError('Empty or non-hierarchy XML')
                except ET.ParseError:
                    last = 'Fresh dump was not valid XML'
                else:
                    subprocess.run(adb + ['shell', 'rm -f ' + path], capture_output=True, timeout=10)
                    return q.stdout
        time.sleep(.3)
    raise RuntimeError('No fresh valid UI hierarchy before deadline: ' + last[-600:])
