"""Host shell-routing tests only; real runtime execution is covered on Android."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ENTRY = Path(__file__).resolve().parents[2] / 'common/luoshu_composite.sh'


class CompositeEntryTest(unittest.TestCase):
    def invoke(self, arch='x86_64', qemu='1', bridge='libndk_translation.so', enabled='1', runtime_ok=True):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bin_dir = root / 'bin'
            bin_dir.mkdir()
            runtime = root / 'common/python/bin'
            runtime.mkdir(parents=True)
            scripts = {
                bin_dir / 'uname': '#!/bin/sh\nprintf "%s\\n" "$TEST_ARCH"\n',
                bin_dir / 'getprop': '#!/bin/sh\ncase "$1" in ro.kernel.qemu) echo "$TEST_QEMU";; ro.enable.native.bridge.exec) echo "$TEST_ENABLED";; ro.dalvik.vm.native.bridge) echo "$TEST_BRIDGE";; esac\n',
                runtime / 'luoshu-python': '#!/bin/sh\nexit "$TEST_RUNTIME_EXIT"\n',
            }
            for path, script in scripts.items():
                path.write_text(script)
                path.chmod(0o700)
            env = dict(os.environ, MODDIR=str(root), PATH=str(bin_dir) + ':' + os.environ['PATH'],
                       TEST_ARCH=arch, TEST_QEMU=qemu, TEST_BRIDGE=bridge, TEST_ENABLED=enabled,
                       TEST_RUNTIME_EXIT='0' if runtime_ok else '1')
            return subprocess.run(['sh', str(ENTRY), '--self-test'], env=env, capture_output=True).returncode

    def test_native_arm_path_remains_allowed(self):
        self.assertEqual(self.invoke(arch='aarch64', qemu='0', bridge='0'), 0)

    def test_verified_emulator_route(self):
        self.assertEqual(self.invoke(), 0)

    def test_non_emulator_x86_rejected(self):
        self.assertEqual(self.invoke(qemu='0'), 21)

    def test_absent_native_bridge_rejected(self):
        self.assertEqual(self.invoke(bridge='0'), 21)
        self.assertEqual(self.invoke(enabled='0'), 21)

    def test_actual_runtime_failure_rejected(self):
        self.assertEqual(self.invoke(runtime_ok=False), 21)

    def test_other_arch_rejected(self):
        self.assertEqual(self.invoke(arch='riscv64'), 21)
