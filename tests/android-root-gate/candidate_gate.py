#!/usr/bin/env python3
"""Evidence-first candidate checks on the already qualified disposable AVD.

Partial checks are useful evidence, but missing end-to-end requirements stay
BLOCKED and this command exits nonzero. Never replaces shipped runtime or uname.
"""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import shlex
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
import zipfile

from probe import BASELINE_SHA256
from adb_ui import dump_ui

DEVICE = '/data/local/tmp/luoshu-candidate-gate'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract(archive, dest):
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            p = Path(info.filename)
            if p.is_absolute() or '..' in p.parts:
                raise RuntimeError('Unsafe ZIP member')
            if info.is_dir():
                continue
            target = dest / p
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(z.read(info))
            if info.external_attr >> 16 & 0o111:
                target.chmod(0o755)


def app_launch_result(package, launch_output, logcat, hierarchy, process_alive):
    if re.search(r'Process: ' + re.escape(package) + r', PID:', logcat) and 'FATAL EXCEPTION:' in logcat:
        return {'result': 'FAIL', 'reason': 'Actual candidate App fatal exception in logcat'}
    if not process_alive:
        return {'result': 'FAIL', 'reason': 'Candidate process exited after launch'}
    if "System UI isn't responding" in hierarchy or 'System UI is not responding' in hierarchy:
        return {'result': 'BLOCKED', 'reason': 'System UI ANR prevents App UI validation', 'environment_system_ui_anr': True}
    if "isn't responding" in hierarchy or 'is not responding' in hierarchy:
        return {'result': 'FAIL', 'reason': 'Application ANR dialog prevents UI validation'}
    if 'Status: ok' not in launch_output:
        return {'result': 'FAIL', 'reason': 'Android activity launch failed'}
    if 'permissioncontroller' in hierarchy:
        return {'result': 'BLOCKED', 'reason': 'Permission dialog, not candidate content, is visible'}
    if package not in hierarchy:
        return {'result': 'BLOCKED', 'reason': 'Candidate UI is not visible'}
    return {'result': 'PASS', 'note': 'App launch only; not Root access or usable font-library performance'}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline-zip', required=True, type=Path)
    parser.add_argument('--candidate-zip', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = {'schema': 1, 'delivery_gate': 'BLOCKED', 'steps': [], 'checks': {},
              'baseline_zip_sha256': sha(args.baseline_zip), 'candidate_zip_sha256': sha(args.candidate_zip)}
    adb = [os.environ.get('ADB', 'adb'), '-s', 'emulator-5554']

    def run(arguments, timeout=60, required=True):
        p = subprocess.run(adb + arguments, capture_output=True, text=True, timeout=timeout)
        report['steps'].append({'argv': arguments, 'exit': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr})
        if required and p.returncode:
            raise RuntimeError('ADB failed: ' + shlex.join(arguments))
        return p

    try:
        if report['baseline_zip_sha256'] != BASELINE_SHA256:
            raise RuntimeError('Baseline hash mismatch')
        if run(['shell', 'getprop ro.kernel.qemu']).stdout.strip() != '1':
            raise RuntimeError('Disposable emulator required')
        if run(['shell', 'id -u']).stdout.strip() != '0':
            raise RuntimeError('Root adb required')
        report['selinux'] = run(['shell', 'getenforce']).stdout.strip()
        report['root_manager_probe'] = run(['shell', 'command -v su; command -v magisk; '
            'command -v ksud; ls -ld /data/adb/modules /data/adb/magisk /data/adb/ksu 2>/dev/null'], required=False).stdout
        su_help = run(['shell', '/system/xbin/su --help'], required=False)
        su_command = run(['shell', '/system/xbin/su -c id'], required=False)
        report['su_cli_probe'] = {'caller': 'adb root, not App UID',
            'help_exit': su_help.returncode, 'help': su_help.stdout + su_help.stderr,
            'root_shell_syntax_exit': su_command.returncode,
            'root_shell_syntax_output': su_command.stdout + su_command.stderr}
        with tempfile.TemporaryDirectory(prefix='luoshu-candidate-') as tmp:
            root = Path(tmp)
            for name, archive in [('baseline', args.baseline_zip), ('candidate', args.candidate_zip)]:
                module = root / name
                extract(archive, module)
                elf = module / 'common/python/bin/luoshu-python'
                data = elf.read_bytes()
                if data[:4] != b'\x7fELF' or int.from_bytes(data[18:20], 'little') != 183:
                    raise RuntimeError(name + ' is not original ARM64 runtime')
                report[name + '_launcher_sha256'] = sha(elf)
                run(['shell', 'mkdir -p ' + DEVICE])
                run(['push', str(module), DEVICE + '/' + name], timeout=180)
                remote = DEVICE + '/' + name
                run(['shell', 'chmod 755 ' + remote + '/common/python/bin/luoshu-python'])
                entry = run(['shell', 'MODDIR=' + remote + ' sh ' + remote + '/common/luoshu_composite.sh --self-test'], required=False)
                report['checks'][name + '_official_composite_entry'] = {'result': 'PASS' if entry.returncode == 0 else 'BLOCKED',
                    'exit': entry.returncode, 'stdout': entry.stdout, 'stderr': entry.stderr}
            helper = root / 'candidate/common/task_scope.py'
            report['candidate_helper_sha256'] = sha(helper)
            test = Path(__file__).with_name('task_scope_device.py')
            run(['push', str(test), DEVICE + '/task_scope_device.py'])
            remote = DEVICE + '/candidate'
            runtime = remote + '/common/python'
            command = (f'PYTHONHOME={runtime} PYTHONPATH={runtime}/lib/python3.14:{runtime}/lib/python3.14/site-packages '
                       f'LD_LIBRARY_PATH={runtime}/lib:{runtime}/lib/python3.14/lib-dynload '
                       f'TMPDIR=/data/local/tmp {runtime}/bin/luoshu-python {DEVICE}/task_scope_device.py '
                       f'--helper {remote}/common/task_scope.py --output {DEVICE}/scope-result.json')
            scope_result = run(['shell', command], timeout=180, required=False)
            raw = run(['shell', 'cat ' + DEVICE + '/scope-result.json'], required=False)
            if raw.returncode == 0:
                report['checks']['candidate_scope'] = json.loads(raw.stdout)
            else:
                report['checks']['candidate_scope'] = {'result': 'FAIL', 'exit': scope_result.returncode}
            apk = root / 'candidate/bundled/LuoShu-App.apk'
            report['candidate_apk_sha256'] = sha(apk)
            run(['install', '-r', str(apk)], timeout=120)
            package = 'io.github.xgl34222220.luoshu.stabletest'
            run(['shell', 'am force-stop ' + package])
            run(['logcat', '-c'])
            launch = run(['shell', 'am start -W -n ' + package + '/io.github.xgl34222220.luoshu.MainActivity'], timeout=60, required=False)
            report['checks']['app_launch_only'] = {'result': 'BLOCKED',
                'note': 'Launch time is not usable font-library performance', 'am_start_output': launch.stdout}
            try:
                hierarchy = subprocess.CompletedProcess([], 0, dump_ui(adb, DEVICE + '/app', report['steps']), '')
            except RuntimeError as error:
                report['ui_observation_error'] = str(error)
                hierarchy = subprocess.CompletedProcess([], 1, '', str(error))
            # Decline only the nonessential notification request in this fresh
            # disposable test installation. Never grant unexpected permissions.
            if ('permissioncontroller' in hierarchy.stdout and
                    ('notification' in hierarchy.stdout.lower() or '通知' in hierarchy.stdout)):
                xml = ET.fromstring(hierarchy.stdout)
                for node in xml.iter('node'):
                    if node.get('resource-id', '').endswith('/permission_deny_button'):
                        bounds = re.fullmatch(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', node.get('bounds', ''))
                        if bounds:
                            x1, y1, x2, y2 = map(int, bounds.groups())
                            run(['shell', f'input tap {(x1+x2)//2} {(y1+y2)//2}'])
                            time.sleep(2)
                            try:
                                hierarchy = subprocess.CompletedProcess([], 0, dump_ui(adb, DEVICE + '/app', report['steps']), '')
                            except RuntimeError as error:
                                report['ui_observation_error'] = str(error)
                                hierarchy = subprocess.CompletedProcess([], 1, '', str(error))
                        break
            (args.output / 'candidate-app.xml').write_text(hierarchy.stdout)
            logs = run(['logcat', '-d', '-s', 'LuoShuStartup:I', 'AndroidRuntime:E', '*:S'], required=False)
            (args.output / 'candidate-app.log').write_text(logs.stdout)
            last_anr = run(['shell', 'dumpsys activity lastanr'], timeout=45, required=False)
            (args.output / 'android-last-anr.txt').write_text(last_anr.stdout + last_anr.stderr)
            system_log = run(['logcat', '-b', 'system', '-d', '-v', 'threadtime'], timeout=45, required=False)
            (args.output / 'android-system.log').write_text(system_log.stdout)
            alive = run(['shell', 'pidof ' + package], required=False)
            report['checks']['app_launch_only'] = app_launch_result(
                package, launch.stdout, logs.stdout, hierarchy.stdout, bool(alive.stdout.strip()))
            report['checks']['app_launch_only']['am_start_output'] = launch.stdout
            screenshot = subprocess.run(adb + ['exec-out', 'screencap', '-p'], capture_output=True, timeout=30)
            if screenshot.returncode == 0:
                (args.output / 'candidate-app.png').write_bytes(screenshot.stdout)
        report['checks']['app_uid_to_su'] = {'result': 'BLOCKED',
            'reason': ('Installed su rejects the actual RootShell su -c syntax even from adb root'
                       if report['su_cli_probe']['root_shell_syntax_exit'] != 0
                       else 'su syntax works from adb root; actual App UID/domain grant still unproven'),
            'note': 'No shell-UID result is treated as an App root grant'}
        report['checks']['module_install_boot_hooks'] = {'result': 'BLOCKED', 'reason': 'No supported module-manager installation was performed'}
        report['checks']['font_mount_rollback_reboot'] = {'result': 'BLOCKED', 'reason': 'Original module lifecycle not yet installed/validated'}
        report['checks']['cold_warm_large_library'] = {'result': 'BLOCKED', 'reason': 'Root data access and synthetic inventory readiness not yet proven'}
    except Exception as error:
        report['error'] = str(error)
    finally:
        (args.output / 'candidate-gate.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'delivery_gate': report['delivery_gate'], 'checks': report['checks']}, ensure_ascii=False))
    return 1  # Missing complete end-to-end evidence must never turn this gate green.


if __name__ == '__main__':
    raise SystemExit(main())
