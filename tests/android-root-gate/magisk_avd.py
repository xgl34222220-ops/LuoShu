#!/usr/bin/env python3
"""Prepare an authorized disposable AVD ramdisk copy using official Magisk 30.7.

Never flashes a physical device or rewrites the SDK image. No live_setup script,
setenforce, verity disabling, host permission change, or blanket root grant.
"""
import hashlib
import json
import os
import re
import shlex
from pathlib import Path
import subprocess
import zipfile

APK_SHA256 = 'e0d32d2123532860f97123d927b1bb86c4e08e6fd8a48bfc6b5bee0afae9ebd5'
PATCH_SHA256 = '1720669a684f75fe90a7318868dd4528f2e736a5ad5363f92a3c51c848d79703'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def prepare(apk, patch_script, sdk, output, adb):
    output = Path(output)
    report = {'version': '30.7', 'result': 'FAIL', 'steps': []}
    def run(args, timeout=90):
        p = subprocess.run([adb, '-s', 'emulator-5554'] + args, capture_output=True, text=True, timeout=timeout)
        report['steps'].append({'argv': args, 'exit': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr})
        if p.returncode:
            raise RuntimeError('Magisk preparation command failed: ' + str(args))
        return p.stdout.strip()
    try:
        if digest(apk) != APK_SHA256 or digest(patch_script) != PATCH_SHA256:
            raise RuntimeError('Official Magisk input checksum mismatch')
        if run(['shell', 'getprop ro.kernel.qemu']) != '1':
            raise RuntimeError('Disposable AVD only')
        if run(['shell', 'getenforce']) != 'Enforcing':
            raise RuntimeError('SELinux must already be Enforcing')
        if run(['shell', 'getprop ro.product.cpu.abi']) != 'x86_64':
            raise RuntimeError('Pinned Magisk AVD recipe requires x86_64 system image')
        ramdisk = Path(sdk) / 'system-images/android-35/google_apis/x86_64/ramdisk.img'
        original = digest(ramdisk)
        private = Path(os.environ['ANDROID_AVD_HOME']) / 'magisk-input'
        private.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(apk) as z:
            (private / 'busybox').write_bytes(z.read('lib/x86_64/libbusybox.so'))
        # Patching happens against a copied guest file, never the installed SDK.
        run(['push', str(private / 'busybox'), '/data/local/tmp/busybox'])
        run(['push', str(apk), '/data/local/tmp/magisk.apk'])
        run(['push', str(patch_script), '/data/local/tmp/host_patch.sh'])
        run(['push', str(ramdisk), '/data/local/tmp/luoshu-ramdisk.img'])
        run(['install', '-r', str(apk)], timeout=120)
        run(['shell', 'sh /data/local/tmp/host_patch.sh /data/local/tmp/luoshu-ramdisk.img'], timeout=180)
        patched = private / 'ramdisk-magisk.img'
        run(['pull', '/data/local/tmp/luoshu-ramdisk.img.magisk', str(patched)])
        if digest(ramdisk) != original:
            raise RuntimeError('Original SDK ramdisk changed')
        report.update(result='PASS', original_ramdisk_sha256=original, patched_ramdisk_sha256=digest(patched),
                      apk_sha256=APK_SHA256, patch_script_sha256=PATCH_SHA256,
                      keepverity=True, keepforceencrypt=True)
        return patched
    finally:
        (output / 'magisk-preparation.json').write_text(json.dumps(report, indent=2) + '\n')


def verify(adb, output):
    report = {'result': 'FAIL', 'steps': []}
    def run(command, required=True):
        p = subprocess.run([adb, '-s', 'emulator-5554', 'shell', command], capture_output=True, text=True, timeout=60)
        report['steps'].append({'command': command, 'exit': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr})
        if required and p.returncode:
            raise RuntimeError('Patched AVD verification failed: ' + command)
        return p.stdout.strip()
    try:
        if run('getprop ro.kernel.qemu') != '1' or run('getenforce') != 'Enforcing':
            raise RuntimeError('AVD identity or SELinux invariant failed')
        report['boot_id'] = run('cat /proc/sys/kernel/random/boot_id')
        report['path'] = run('echo "$PATH"')
        report['kernel_cmdline'] = run('cat /proc/cmdline', required=False)
        report['boot_processes'] = run('ps -A -o PID,PPID,NAME,ARGS', required=False)
        report['known_locations'] = run('ls -la /debug_ramdisk /sbin /data/adb /data/adb/magisk /data/local/tmp/magisk 2>&1', required=False)
        report['mountinfo'] = run('cat /proc/1/mountinfo', required=False)
        report['kernel_log'] = run('dmesg', required=False)
        report['magisk_log'] = run('cat /cache/magisk.log /data/adb/magisk.log 2>/dev/null', required=False)
        magisk = run('command -v magisk', required=False)
        if not magisk:
            magisk = run('for f in /debug_ramdisk/magisk /sbin/magisk /data/adb/magisk/magisk; do if [ -x "$f" ]; then echo "$f"; break; fi; done', required=False)
        # Querying a standalone binary can start a daemon. Require a daemon to
        # already exist at boot before invoking any Magisk client, so manual
        # daemon startup is never mistaken for real magiskinit boot integration.
        if not re.search(r'^\s*\d+\s+\d+\s+magiskd(?:\s|$)', report['boot_processes'], re.M):
            raise RuntimeError('Patched Android booted, but no pre-existing magiskd was observed')
        if not magisk:
            raise RuntimeError('Magisk daemon exists but no standard client location is visible')
        version = run(shlex.quote(magisk) + ' -v')
        if '30.7' not in version:
            raise RuntimeError('Unexpected Magisk runtime version')
        env_state = run('if [ -s /data/adb/magisk/util_functions.sh ] && [ -x /data/adb/magisk/busybox ]; then echo ready; else echo missing; fi')
        report['environment_before_setup'] = env_state
        if env_state != 'ready':
            complete_setup(adb, output)
            report['post_setup_processes'] = run('ps -A -o PID,PPID,NAME,ARGS')
            if not re.search(r'^\s*\d+\s+\d+\s+magiskd(?:\s|$)', report['post_setup_processes'], re.M):
                raise RuntimeError('Magisk daemon missing after official setup reboot')
            if run('getenforce') != 'Enforcing':
                raise RuntimeError('SELinux invariant failed after official setup')
        run('test -s /data/adb/magisk/util_functions.sh && test -x /data/adb/magisk/busybox')
        report['plain_adb_su'] = run('command -v su; su -c id -u', required=False)
        # Use the existing real Magisk client for admin/module checks. This does
        # not alter PATH or claim that the App can resolve or use this client.
        uid = run(shlex.quote(magisk) + " su -c 'id -u'")
        if uid != '0':
            raise RuntimeError('Magisk su shell capability failed')
        report.update(result='PASS', magisk=magisk, version=version, shell_root=True,
                      app_root='NOT_GRANTED_OR_PROVEN', module_boot_hooks='Pending real module lifecycle test')
        return magisk
    finally:
        (Path(output) / 'magisk-boot.json').write_text(json.dumps(report, indent=2) + '\n')


def reviewed_setup_prompt(text):
    value = text.lower()
    return ('requires additional setup' in value and
            'your device needs additional setup for magisk to work properly. do you want to proceed and reboot?' in value)


def complete_setup(adb, output):
    """Complete only the official manager's expected additional-setup dialog."""
    from adb_ui import dump_ui
    from adb_utils import ensure_root
    import time
    import xml.etree.ElementTree as ET
    report = {'result': 'FAIL', 'steps': []}
    output = Path(output)
    target = [adb, '-s', 'emulator-5554']
    def run(args, required=True, timeout=60):
        try:
            p = subprocess.run(target + args, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            report['steps'].append({'argv': args, 'result': 'TRANSPORT_TIMEOUT'})
            if required:
                raise
            return ''
        report['steps'].append({'argv': args, 'exit': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr})
        if required and p.returncode:
            raise RuntimeError('Official Magisk manager setup failed: ' + str(args))
        return p.stdout.strip()
    def snapshot(label):
        text = dump_ui(target, '/data/local/tmp/luoshu-magisk-ui', report['steps'])
        (output / (label + '.xml')).write_text(text)
        p = subprocess.run(target + ['exec-out', 'screencap', '-p'], capture_output=True, timeout=30)
        if p.returncode == 0:
            (output / (label + '.png')).write_bytes(p.stdout)
        return ET.fromstring(text)
    def tap(node):
        bounds = re.fullmatch(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', node.get('bounds', ''))
        if not bounds:
            raise RuntimeError('Expected setup control has no verified screen bounds')
        x1, y1, x2, y2 = map(int, bounds.groups())
        run(['shell', f'input tap {(x1+x2)//2} {(y1+y2)//2}'])
    try:
        before = run(['shell', 'cat /proc/sys/kernel/random/boot_id'])
        run(['shell', 'am start -W -a android.intent.action.MAIN -c android.intent.category.LAUNCHER -p com.topjohnwu.magisk'])
        tree = snapshot('magisk-manager-before')
        texts = ' '.join(n.get('text', '') for n in tree.iter('node'))
        if 'notification' in texts.lower():
            deny = [n for n in tree.iter('node') if n.get('resource-id', '').endswith('/permission_deny_button')]
            if deny:
                tap(deny[0]); time.sleep(1)
                tree = snapshot('magisk-manager-notifications-declined')
                texts = ' '.join(n.get('text', '') for n in tree.iter('node'))
        if not reviewed_setup_prompt(texts):
            raise RuntimeError('Exact reviewed setup-and-reboot prompt not observed; no other control accepted')
        buttons = [n for n in tree.iter('node') if n.get('text', '').strip().lower() == 'ok'
                   and n.get('package') in ('com.topjohnwu.magisk', 'android') and n.get('enabled') != 'false']
        if len(buttons) != 1:
            raise RuntimeError('Official setup confirmation is not unique')
        report['accepted_dialog_text'] = texts
        tap(buttons[0])
        end = time.monotonic() + 240
        while time.monotonic() < end:
            boot = run(['shell', 'cat /proc/sys/kernel/random/boot_id'], required=False, timeout=15)
            if re.fullmatch(r'[0-9a-f-]{36}', boot) and boot != before and run(['shell', 'getprop sys.boot_completed'], required=False, timeout=15) == '1':
                ensure_root(target, report['steps'])
                if run(['shell', 'getenforce']) != 'Enforcing':
                    raise RuntimeError('SELinux changed during official setup')
                report.update(result='PASS', boot_id_before=before, boot_id_after=boot)
                return
            time.sleep(2)
        snapshot('magisk-manager-setup-timeout')
        raise RuntimeError('Official additional setup did not produce a verified completed reboot')
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        (output / 'magisk-manager-setup.json').write_text(json.dumps(report, indent=2) + '\n')
