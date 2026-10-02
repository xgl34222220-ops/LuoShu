#!/usr/bin/env python3
"""Evidence-first candidate checks on the already qualified disposable AVD.

Partial checks are useful evidence, but missing end-to-end requirements stay
BLOCKED and this command exits nonzero. Never replaces shipped runtime or uname.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import zipfile

from probe import BASELINE_SHA256

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
            launch = run(['shell', 'am start -W -n ' + package + '/io.github.xgl34222220.luoshu.MainActivity'], timeout=60, required=False)
            report['checks']['app_launch_only'] = {'result': 'PASS' if launch.returncode == 0 and 'Status: ok' in launch.stdout else 'FAIL',
                'note': 'Launch time is not usable font-library performance', 'am_start_output': launch.stdout}
            run(['shell', 'uiautomator dump ' + DEVICE + '/app.xml'], timeout=45, required=False)
            hierarchy = run(['shell', 'cat ' + DEVICE + '/app.xml'], required=False)
            (args.output / 'candidate-app.xml').write_text(hierarchy.stdout)
            logs = run(['logcat', '-d', '-s', 'LuoShuStartup:I', 'AndroidRuntime:E', '*:S'], required=False)
            (args.output / 'candidate-app.log').write_text(logs.stdout)
            screenshot = subprocess.run(adb + ['exec-out', 'screencap', '-p'], capture_output=True, timeout=30)
            if screenshot.returncode == 0:
                (args.output / 'candidate-app.png').write_bytes(screenshot.stdout)
        report['checks']['app_uid_to_su'] = {'result': 'BLOCKED', 'reason': 'Not proven from the actual App UID/domain; adb root is not App root'}
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
