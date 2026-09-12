#!/usr/bin/env python3
"""The public axis bridge must preserve analyzer output and execution failures."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class WeightAxisBridgeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.module = Path(self.temp.name) / 'module'
        self.common = self.module / 'common'
        self.common.mkdir(parents=True)
        for filename in ('app_bridge.sh', 'util_functions.sh',
                         'util_functions_core.sh', 'font_axis_info.py'):
            shutil.copyfile(ROOT / 'common' / filename, self.common / filename)
        (self.module / 'module.prop').write_text('id=LuoShu\n', encoding='utf-8')
        self.public = Path(self.temp.name) / 'public'
        (self.public / 'fonts').mkdir(parents=True)
        self.source = self.public / 'fonts' / '鸿蒙保时捷可变VF.ttf'
        self.source.write_bytes(b'font-source-fixture')
        self.launcher = self.common / 'python/bin/luoshu-python'
        self.launcher.parent.mkdir(parents=True)
        self.launcher.write_text(
            '#!/bin/sh\n'
            'printf "%s" "$AXIS_TEST_STDOUT"\n'
            'printf "%s" "$AXIS_TEST_STDERR" >&2\n'
            'exit "$AXIS_TEST_EXIT"\n', encoding='utf-8')
        self.launcher.chmod(0o755)
        self.env = dict(os.environ, MODDIR=str(self.module),
                        MODULE_DIR=str(self.module),
                        LUOSHU_PUBLIC_DIR=str(self.public),
                        AXIS_TEST_STDOUT='', AXIS_TEST_STDERR='', AXIS_TEST_EXIT='0')

    def run_bridge(self, stdout='', stderr='', code=0):
        return subprocess.run(
            ['sh', str(self.common / 'app_bridge.sh'), 'weight_axis', '鸿蒙保时捷可变VF'],
            env=dict(self.env, AXIS_TEST_STDOUT=stdout,
                     AXIS_TEST_STDERR=stderr, AXIS_TEST_EXIT=str(code)),
            capture_output=True, text=True, timeout=10)

    def test_successful_variable_capability_is_unchanged(self):
        output = '{"status":"ok","variable":true,"hasWeight":true,"weight":{"tag":"wght","min":100,"default":400,"max":900}}\n'
        result = self.run_bridge(output)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, output, ''))

    def test_successful_static_capability_is_unchanged(self):
        output = '{"status":"ok","variable":false,"hasWeight":false,"weight":null,"axes":[]}\n'
        result = self.run_bridge(output)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, output, ''))

    def test_python_launch_failure_keeps_nonzero_exit_and_stderr(self):
        result = self.run_bridge(stderr='LuoShu: unable to load libpython\n', code=97)
        self.assertEqual(result.returncode, 97)
        self.assertEqual(result.stdout, '')
        self.assertEqual(result.stderr, 'LuoShu: unable to load libpython\n')

    def test_analyzer_error_keeps_json_and_nonzero_exit(self):
        output = '{"status":"error","message":"font could not be read"}\n'
        result = self.run_bridge(output, code=1)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (1, output, ''))

    def test_missing_source_stays_an_error(self):
        self.source.unlink()
        result = self.run_bridge()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)['message'], '找不到字体轴来源')

    def test_unavailable_analyzer_stays_an_error(self):
        self.launcher.unlink()
        result = self.run_bridge()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)['message'], '字体轴分析器不可用')


if __name__ == '__main__':
    unittest.main()
