#!/usr/bin/env python3
"""Prepare an authorized disposable AVD ramdisk copy using official Magisk 30.7.

Never flashes a physical device or rewrites the SDK image. No live_setup script,
setenforce, verity disabling, host permission change, or blanket root grant.
"""
import hashlib
import json
import os
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
    def run(command):
        p = subprocess.run([adb, '-s', 'emulator-5554', 'shell', command], capture_output=True, text=True, timeout=60)
        report['steps'].append({'command': command, 'exit': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr})
        if p.returncode:
            raise RuntimeError('Patched AVD verification failed: ' + command)
        return p.stdout.strip()
    try:
        if run('getprop ro.kernel.qemu') != '1' or run('getenforce') != 'Enforcing':
            raise RuntimeError('AVD identity or SELinux invariant failed')
        magisk = run('command -v magisk')
        version = run(magisk + ' -v')
        if '30.7' not in version:
            raise RuntimeError('Unexpected Magisk runtime version')
        uid = run('su -c id -u')
        if uid != '0':
            raise RuntimeError('Magisk su shell capability failed')
        report.update(result='PASS', magisk=magisk, version=version, shell_root=True,
                      app_root='NOT_GRANTED_OR_PROVEN')
        return magisk
    finally:
        (Path(output) / 'magisk-boot.json').write_text(json.dumps(report, indent=2) + '\n')
