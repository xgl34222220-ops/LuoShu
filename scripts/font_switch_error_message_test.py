#!/usr/bin/env python3
"""Regression for the Android toybox sed crash in switch failure handling."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'common/task_scope.py'
spec = importlib.util.spec_from_file_location('task_scope_error_test', HELPER)
scope = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scope)


class ErrorMessageParserTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'manager-output'

    def parse(self, value):
        self.path.write_bytes(value if isinstance(value, bytes) else value.encode())
        return scope.error_message_from_file(self.path)

    def test_chinese_message_preserves_quotes_backslashes_and_unicode(self):
        message = '无法准备“中文字体” "quoted" C:\\fonts\\测试.ttf 😀'
        self.assertEqual(self.parse(json.dumps({'status': 'error', 'message': message})), message)

    def test_noise_and_malformed_records_do_not_hide_last_valid_message(self):
        text = '\n'.join(('normal log', '{"message":"first"}', 'not JSON "message":"fake"',
                           '{ "status": "error", "message": "last" }', '{"message":invalid}'))
        self.assertEqual(self.parse(text), 'last')

    def test_pretty_json_and_top_level_only(self):
        value = {'status': 'error', 'nested': {'message': 'wrong'}, 'message': 'right'}
        self.assertEqual(self.parse(json.dumps(value, indent=2)), 'right')
        self.assertEqual(self.parse('{"nested":{"message":"wrong"}}'), '')
        self.assertEqual(self.parse('[\n {"message":"wrong"}\n]'), '')

    def test_controls_cannot_inject_task_fields(self):
        message = 'failed\r\nstate=success\x00\tmore\x7f\x85\u2028\u2029'
        self.assertEqual(self.parse(json.dumps({'message': message})), 'failed  state=success  more')

    def test_missing_invalid_nonstring_and_deep_input_fail_quietly(self):
        self.assertEqual(scope.error_message_from_file(self.path), '')
        for data in ('', 'not json', '{"message":null}', '{"message":[]}',
                     '{"message":42}', '{"message":""}', '{"x":' + '[' * 5000 + '0' + ']' * 5000 + '}'):
            with self.subTest(data=data[:60]):
                self.assertEqual(self.parse(data), '')

    def test_multimegabyte_noise_reads_only_tail_and_bounds_message(self):
        self.assertEqual(self.parse(b'x' * (2 * 1024 * 1024) + b'\n{"message":"tail"}\n'), 'tail')
        self.assertEqual(self.parse(json.dumps({'message': '中' * 6000})), '中' * 4096)
        self.assertEqual(self.parse(b'{"message":"' + b'x' * (512 * 1024) + b'"}'), '')

    def test_lone_surrogate_and_invalid_utf8_do_not_crash_stdout(self):
        self.assertEqual(self.parse(b'{"message":"\\ud800"}'), '?')
        self.assertEqual(self.parse(b'{"message":"bad-\xff"}'), 'bad-\ufffd')


class SwitchFailurePathTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.module = self.root / 'module'
        (self.module / 'common').mkdir(parents=True)
        (self.module / 'config').mkdir()
        (self.module / 'logs').mkdir()
        shutil.copyfile(ROOT / 'common/background_task.sh', self.module / 'common/background_task.sh')
        self.output = self.root / 'manager-output'
        self.manager = self.root / 'manager.sh'
        self.manager.write_text('#!/bin/sh\ncat "$ERROR_RESPONSE"\nexit 7\n')
        binary = self.root / 'bin'
        binary.mkdir()
        sed = binary / 'sed'
        # Reproduce the dangerous call as a hard test failure without requiring
        # a host to share Android's broken libc implementation. All other sed
        # invocations remain real, so this exercises the real shell error path.
        sed.write_text('#!/bin/sh\ncase "$*" in *\'"message":"\'*) '
                       'echo forbidden > "$SED_CRASH_MARKER"; exit 99;; esac\n'
                       'exec "$REAL_SED" "$@"\n')
        sed.chmod(0o755)
        self.marker = self.root / 'forbidden-sed'
        self.env = dict(os.environ, MODDIR=str(self.module),
                        LUOSHU_FONT_MANAGER=str(self.manager), LUOSHU_TASK_HELPER=str(HELPER),
                        LUOSHU_SWITCH_TASK_FILE=str(self.module / 'config/switch_task.conf'),
                        LUOSHU_SWITCH_WORKER_PID_FILE=str(self.module / 'config/switch_task_worker.pid'),
                        LUOSHU_SWITCH_LOG=str(self.module / 'logs/fontswitch.log'),
                        ERROR_RESPONSE=str(self.output), SED_CRASH_MARKER=str(self.marker),
                        REAL_SED=shutil.which('sed'), PATH=str(binary) + ':' + os.environ['PATH'])

    def run_failure(self, response, helper=None):
        self.output.write_text(response)
        env = self.env.copy()
        if helper is not None:
            env['LUOSHU_TASK_HELPER'] = helper
        process = subprocess.run(['sh', str(ROOT / 'common/font_switch_task.sh'), 'run',
                                  'failure-regression', 'test-font', '1'],
                                 env=env, text=True, capture_output=True, timeout=8)
        self.assertEqual(process.returncode, 0, process.stderr)
        values = dict(line.split('=', 1) for line in
                      (self.module / 'config/switch_task.conf').read_text().splitlines() if '=' in line)
        self.assertEqual(values['state'], 'failed')
        self.assertEqual(values['percent'], '100')
        self.assertFalse(self.marker.exists(), 'failure path invoked the crash-prone sed expression')
        self.assertFalse(list((self.module / 'config').glob('*.output.*')))
        self.assertFalse(list((self.module / 'config').glob('*.progress.*')))
        return values['message']

    def test_real_worker_error_path_preserves_specific_failure_without_sed(self):
        message = '无法创建字体暂存区 "prepare" C:\\fonts\r\n请重试'
        result = self.run_failure('log prefix\n' + json.dumps({'status': 'error', 'message': message}))
        self.assertEqual(result, '无法创建字体暂存区 "prepare" C:\\fonts  请重试')

    def test_invalid_json_keeps_generic_failure_fallback(self):
        self.assertEqual(self.run_failure('broken JSON "message":"'),
                         '字体切换失败（代码 7），当前启动字体未被改动')

    def test_unavailable_parser_keeps_generic_failure_fallback(self):
        self.assertEqual(self.run_failure('{"message":"specific"}', '/missing/task_scope.py'),
                         '字体切换失败（代码 7），当前启动字体未被改动')


if __name__ == '__main__':
    unittest.main()
