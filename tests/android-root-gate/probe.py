#!/usr/bin/env python3
"""Qualify a disposable Android AVD. This is NOT the module delivery gate."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import time
import zipfile
from adb_utils import ensure_root

BASELINE_SHA256 = 'c5c8fa86af4ac196107ba05c5ee8cc1944140ae033cc9e763cec8c76f40c848a'
DEVICE = '/data/local/tmp/luoshu-arm64-qualification'
PAYLOAD = r'''
import ctypes, json, os, platform, signal, subprocess, sys
import bz2, lzma, zlib, pyexpat, _posixsubprocess
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
fb = FontBuilder(1000, isTTF=True)
fb.setupGlyphOrder(['.notdef', 'A'])
fb.setupCharacterMap({65: 'A'})
glyphs = {}
for name in ['.notdef', 'A']:
    pen = TTGlyphPen(None)
    pen.moveTo((100, 0)); pen.lineTo((400, 700)); pen.lineTo((700, 0)); pen.closePath()
    glyphs[name] = pen.glyph()
fb.setupGlyf(glyphs)
fb.setupHorizontalMetrics({name: (800, 0) for name in glyphs})
fb.setupHorizontalHeader(ascent=800, descent=-200)
fb.setupNameTable({'familyName': 'LuoShu Synthetic Gate', 'styleName': 'Regular'})
fb.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
fb.setupPost(); fb.setupMaxp()
p = os.path.join(os.path.dirname(__file__), 'synthetic.ttf')
fb.save(p)
with TTFont(p) as font: assert font.getBestCmap()[65] == 'A'
assert subprocess.check_output(['/system/bin/sh', '-c', 'printf android-child']) == b'android-child'
libc = ctypes.CDLL('libc.so', use_errno=True)
assert libc.getpid() == os.getpid()
assert libc.prctl(36, 1, 0, 0, 0) == 0, 'PR_SET_CHILD_SUBREAPER unavailable'
child = os.fork()
if child == 0: os._exit(0)
try:
    waited = os.waitid(os.P_PID, child, os.WEXITED | os.WNOWAIT)
    assert waited.si_pid == child
finally:
    os.waitpid(child, 0)
pidfd = {'python_open_symbol': hasattr(os, 'pidfd_open'), 'python_signal_symbol': hasattr(signal, 'pidfd_send_signal')}
fd = libc.syscall(434, os.getpid(), 0)
pidfd['open_supported'] = fd >= 0
pidfd['open_errno'] = ctypes.get_errno() if fd < 0 else 0
if fd >= 0:
    try:
        sent = libc.syscall(424, fd, 0, None, 0)
        pidfd['send_zero_supported'] = sent == 0
        pidfd['send_zero_errno'] = ctypes.get_errno() if sent < 0 else 0
    finally:
        os.close(fd)
assert zlib.decompress(zlib.compress(b'gate')) == b'gate'
print(json.dumps({'marker': 'ARM64_ELF_EXECUTED', 'python': sys.version, 'machine': platform.machine(), 'fonttools_synthetic_roundtrip': True, 'subprocess': True, 'ctypes': True, 'subreaper': True, 'waitid_wnowait': True, 'pidfd': pidfd}))
'''


def extract_runtime(archive, dest):
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if digest != BASELINE_SHA256:
        raise RuntimeError('Baseline ZIP SHA256 mismatch: ' + digest)
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            if not info.filename.startswith('common/python/') or info.is_dir():
                continue
            relative = Path(info.filename).relative_to('common/python')
            if '..' in relative.parts or relative.is_absolute():
                raise RuntimeError('Unsafe ZIP member')
            target = dest / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(z.read(info))
    elf = (dest / 'bin/luoshu-python').read_bytes()
    if elf[:4] != b'\x7fELF' or int.from_bytes(elf[18:20], 'little') != 183:
        raise RuntimeError('Original launcher is not ARM64 ELF')
    return hashlib.sha256(elf).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--module-zip', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--serial', default='emulator-5554')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report = {'schema': 1, 'qualification': 'FAIL', 'delivery_gate': 'NOT_RUN',
              'baseline_zip_sha256': BASELINE_SHA256, 'steps': []}
    adb = [os.environ.get('ADB', 'adb'), '-s', args.serial]

    def run(arguments, timeout=60):
        try:
            p = subprocess.run(adb + arguments, capture_output=True, text=True, timeout=timeout)
            report['steps'].append({'argv': arguments, 'returncode': p.returncode,
                                    'stdout': p.stdout, 'stderr': p.stderr})
        except subprocess.TimeoutExpired as error:
            report['steps'].append({'argv': arguments, 'result': 'TIMEOUT'})
            raise RuntimeError('ADB operation timed out') from error
        if p.returncode:
            raise RuntimeError('ADB operation failed: ' + shlex.join(arguments))
        return p.stdout.strip()

    def boot():
        run(['wait-for-device'], timeout=180)
        end = time.monotonic() + 180
        while time.monotonic() < end:
            if run(['shell', 'getprop sys.boot_completed']) == '1':
                return
            time.sleep(2)
        raise RuntimeError('Android boot timed out')

    def execute(label):
        command = (f'cd {DEVICE} && PYTHONHOME={DEVICE}/python '
                   f'LD_LIBRARY_PATH={DEVICE}/python/lib '
                   f'{DEVICE}/python/bin/luoshu-python {DEVICE}/probe.py')
        output = run(['shell', command], timeout=90)
        if '"marker": "ARM64_ELF_EXECUTED"' not in output:
            raise RuntimeError('Missing actual ARM64 execution marker')
        report[label] = json.loads(output.splitlines()[-1])

    try:
        # Refuse physical devices even if the caller chooses their serial.
        if run(['shell', 'getprop ro.kernel.qemu']) != '1':
            raise RuntimeError('Only disposable Android emulators are authorized')
        report['device'] = {key: run(['shell', 'getprop ' + key]) for key in
            ['ro.build.fingerprint', 'ro.product.cpu.abilist', 'ro.dalvik.vm.native.bridge',
             'ro.enable.native.bridge.exec', 'ro.build.version.sdk']}
        report['selinux_before'] = run(['shell', 'getenforce'])
        ensure_root(adb, report['steps'])
        if run(['shell', 'id -u']) != '0':
            raise RuntimeError('AVD does not provide root adb')
        with tempfile.TemporaryDirectory(prefix='luoshu-probe-') as tmp:
            root = Path(tmp)
            runtime = root / 'python'
            report['arm64_launcher_sha256'] = extract_runtime(args.module_zip, runtime)
            (root / 'probe.py').write_text(PAYLOAD)
            run(['shell', 'mkdir -p ' + DEVICE])
            run(['push', str(runtime), DEVICE + '/python'], timeout=180)
            run(['push', str(root / 'probe.py'), DEVICE + '/probe.py'])
            run(['shell', 'chmod 755 ' + DEVICE + '/python/bin/luoshu-python'])
            execute('before_reboot')
            report['boot_id_before'] = run(['shell', 'cat /proc/sys/kernel/random/boot_id'])
            run(['reboot']); boot()
            report['boot_id_after'] = run(['shell', 'cat /proc/sys/kernel/random/boot_id'])
            if report['boot_id_before'] == report['boot_id_after']:
                raise RuntimeError('Reboot did not change kernel boot ID')
            ensure_root(adb, report['steps'])
            if run(['shell', 'id -u']) != '0':
                raise RuntimeError('Root unavailable after reboot')
            execute('after_reboot')
        report['selinux_after'] = run(['shell', 'getenforce'])
        if report['selinux_before'] != report['selinux_after']:
            raise RuntimeError('SELinux state changed')
        report['qualification'] = 'PASS'
    except Exception as error:
        report['error'] = str(error)
    finally:
        (args.output / 'qualification.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in ['qualification', 'delivery_gate']}))
    return 0 if report['qualification'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
