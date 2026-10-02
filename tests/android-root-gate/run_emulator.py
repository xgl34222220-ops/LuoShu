#!/usr/bin/env python3
"""One disposable official emulator using the runner's existing sudo policy.

Never alters device permissions, groups, udev, SELinux, or sudoers.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def supervise_root(binary, report):
    """Own the direct child until reaped; sudo forwards termination here."""
    child = None
    result = {'emulator_started': False, 'emulator_reaped': False}
    def stop(signum, frame):
        raise SystemExit(128 + signum)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        child = subprocess.Popen([binary, '-avd', 'luoshu_gate', '-port', '5554',
            '-no-window', '-gpu', 'swiftshader_indirect', '-no-snapshot', '-noaudio',
            '-no-boot-anim', '-camera-back', 'none', '-accel', 'on'])
        result.update(emulator_started=True, pid=child.pid)
        return child.wait()
    finally:
        # Do not interrupt cleanup with a second forwarded cancellation.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        if child is not None:
            if child.poll() is None:
                child.terminate()
            try:
                child.wait(timeout=20)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=10)
            result.update(emulator_reaped=True, returncode=child.returncode)
        Path(report).write_text(json.dumps(result, indent=2) + '\n')


def kvm_state():
    s = os.stat('/dev/kvm')
    return {'uid': s.st_uid, 'gid': s.st_gid, 'mode': s.st_mode & 0o7777, 'rdev': s.st_rdev}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root-supervisor', action='store_true')
    parser.add_argument('--binary')
    parser.add_argument('--cleanup-report')
    parser.add_argument('--module-zip', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.root_supervisor:
        return supervise_root(args.binary, args.cleanup_report)
    args.output.mkdir(parents=True, exist_ok=True)
    output = args.output.resolve()
    sdk = Path(os.environ['ANDROID_HOME']).resolve()
    binary = sdk / 'emulator/emulator'
    if not binary.is_file():
        raise RuntimeError('Official SDK emulator binary missing')
    adb = str(sdk / 'platform-tools/adb')
    env = dict(os.environ, ADB=adb)
    report = {'kvm_before': kvm_state(), 'result': 'FAIL'}
    root_report = output / 'emulator-cleanup.json'
    launcher = None
    def stop(signum, frame):
        raise SystemExit(128 + signum)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        with (output / 'emulator.log').open('w') as log:
            launcher = subprocess.Popen(['sudo', '-n', 'env',
                'HOME=' + os.environ['HOME'],
                'ANDROID_AVD_HOME=' + os.environ['ANDROID_AVD_HOME'],
                'ANDROID_HOME=' + str(sdk), 'ANDROID_SDK_ROOT=' + str(sdk),
                sys.executable, str(Path(__file__).resolve()), '--root-supervisor',
                '--binary', str(binary), '--cleanup-report', str(root_report)], stdout=log, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + 600
            while time.monotonic() < deadline:
                if launcher.poll() is not None:
                    raise RuntimeError('Emulator exited before Android boot; inspect emulator.log')
                result = subprocess.run([adb, '-s', 'emulator-5554', 'shell', 'getprop', 'sys.boot_completed'],
                                        capture_output=True, text=True, timeout=15, env=env)
                if result.returncode == 0 and result.stdout.strip() == '1':
                    break
                time.sleep(2)
            else:
                raise RuntimeError('Android boot timeout after 600 seconds')
            result = subprocess.run([sys.executable, str(Path(__file__).with_name('probe.py')),
                '--module-zip', str(args.module_zip), '--output', str(output)], env=env, timeout=600)
            report['probe_exit'] = result.returncode
            if result.returncode != 0:
                raise RuntimeError('ARM64 Android qualification failed; inspect qualification.json')
            report['result'] = 'PASS'
    except Exception as error:
        report['error'] = str(error)
    finally:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        if launcher is not None:
            try:
                subprocess.run([adb, '-s', 'emulator-5554', 'emu', 'kill'],
                               capture_output=True, timeout=10, env=env)
            except subprocess.TimeoutExpired:
                pass
            if launcher.poll() is None:
                # sudo forwards TERM to our supervisor, which reaps its direct child.
                launcher.terminate()
            try:
                launcher.wait(timeout=45)
            except subprocess.TimeoutExpired:
                report['error'] = 'Root supervisor did not finish cleanup within 45 seconds'
                report['result'] = 'FAIL'
            report['launcher_reaped'] = launcher.poll() is not None
        report['kvm_after'] = kvm_state()
        if report['kvm_before'] != report['kvm_after']:
            report.update(result='FAIL', error='KVM device security metadata changed')
        if not root_report.exists() or not json.loads(root_report.read_text()).get('emulator_reaped'):
            report.update(result='FAIL', error='No confirmed emulator cleanup evidence')
        (output / 'runner-lifecycle.json').write_text(json.dumps(report, indent=2) + '\n')
    return 0 if report['result'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
