#!/usr/bin/env python3
"""Portable installed-engine error-function contracts, not generation/rendering."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile


def run(module, shell):
    android = Path('/system/bin/sh').exists()
    # Extract the actual installed function; sourcing the whole entry executes
    # its command dispatcher. Keep this explicitly separate from CLI generation.
    source = (module / 'common/font_mix.sh').read_text()
    function = source.split('\nextract_composite_error() {', 1)[1].split('\ncheck_composite_runtime() {', 1)[0]
    function = 'extract_composite_error() {' + function
    message = '中文字体 "示例" C:\\Fonts\\测试.ttf 😀'
    cases = [
        ('chinese-native-error', json.dumps({'message': message}, ensure_ascii=False), 1, message, False),
        ('ascii-escaped-error', json.dumps({'message': message}), 1, message, False),
        ('pretty-top-level-error', json.dumps({'message': '正确', 'nested': {'message': '错误'}}, indent=2), 1, '正确', False),
        ('nested-lookalike-error', json.dumps({'message': '正确', 'nested': {'message': '错误'}}), 1, '正确', False),
        ('plain-text-fallback', 'old log\nplain failure\r\n', 1, 'plain failure', False),
        ('unavailable-helper-fallback', 'plain failure\n', 1, 'plain failure', True),
        ('bounded-valid-log-tail', 'x' * (300 * 1024) + '\n{"message":"末条错误"}\n', 1, '末条错误', False),
        ('timeout-code-priority', '{"message":"specific"}', 124, '复合字体生成超过 8 分钟，已安全终止', False),
        ('oom-code-priority', '{"message":"specific"}', 137, '复合字体生成进程被系统终止，通常是内存不足', False),
        ('signal-code-priority', '{"message":"specific"}', 9, '复合字体生成进程被系统终止，通常是内存不足', False),
        ('no-execute-code-priority', '{"message":"specific"}', 126, '复合字体运行程序没有执行权限', False),
        ('runtime-code-priority', '{"message":"specific"}', 127, '复合字体运行时无法启动', False),
        ('missing-runtime-code-priority', '{"message":"specific"}', 20, '复合字体运行时文件缺失', False),
        ('wrong-abi-code-priority', '{"message":"specific"}', 21, '当前设备不是 ARM64，无法运行复合字体引擎', False),
        ('empty-default-error', '', 7, '完整复合字体生成失败（底层返回 7）', False),
    ]
    report = {'schema': 'luoshu-composite-error-contract-v1', 'environment': 'ANDROID' if android else 'HOST_ONLY',
              'module': str(module), 'shell': shell, 'result': 'PASS', 'cases': []}
    with tempfile.TemporaryDirectory(prefix='luoshu-composite-error-', dir='/data/local/tmp' if android else None) as temp:
        base = Path(temp); error = base / 'error-output'; script = base / 'error-function.sh'
        script.write_text('. "$MODDIR/common/background_task.sh"\n' + function +
                          '\n[ "$3" != unavailable ] || luoshu_task_helper() { return 127; }; '
                          'extract_composite_error "$1" "$2"\n')
        env = dict(os.environ, MODDIR=str(module), LUOSHU_TASK_HELPER=str(module / 'common/task_scope.py'))
        for name, data, code, expected, unavailable in cases:
            error.write_text(data)
            result = subprocess.run([shell, str(script), str(error), str(code), 'unavailable' if unavailable else 'available'],
                                    env=env, capture_output=True, text=True, timeout=20)
            if result.returncode != 0 or result.stdout != expected or result.stderr:
                raise RuntimeError(f'{name}: {result.returncode}, {result.stdout!r}, {result.stderr!r}')
            report['cases'].append({'name': name, 'result': 'PASS'})
    report['case_count'] = len(report['cases'])
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--module', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--shell', default='/system/bin/sh' if Path('/system/bin/sh').exists() else 'sh')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    value = json.dumps(run(args.module.resolve(), args.shell), ensure_ascii=False, separators=(',', ':')) + '\n'
    if args.output: args.output.write_text(value)
    print(value, end='')
