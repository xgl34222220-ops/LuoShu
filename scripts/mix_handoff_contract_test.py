#!/usr/bin/env python3
"""Exercise shipped shell handoff/JSON readers on a host or isolated Android.

No unittest dependency: the same cases run under the shipped ARM64 Python.
Fixtures live only in one owned temporary directory, never in module config.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time


def run_cases(module, shell):
    results = []
    started = time.monotonic()
    env = dict(os.environ, MODDIR=str(module), LUOSHU_TASK_HELPER=str(module / 'common/task_scope.py'))
    prefix = '. "$MODDIR/common/background_task.sh"; . "$MODDIR/common/mix_task_handoff.sh"; '
    with tempfile.TemporaryDirectory(prefix='luoshu-handoff-contract-') as directory:
        root = Path(directory)
        response, task = root / 'response.log', root / 'mix_task.conf'

        def call(command, *arguments):
            return subprocess.run([shell, '-c', prefix + command, 'handoff-test', *map(str, arguments)],
                                  env=env, capture_output=True, text=True, timeout=25)

        base = dict(task='new-task', state='running', cjk='CJK', latin='Latin', digit='Digit')
        handoffs = [
            ('silent-start', '', {}, 'new-task'),
            ('conflicting-output', '{"status":"ok","data":{"task":"other-task"}}', {}, 'new-task'),
            ('truncated-output', '{"status":"ok","data":{"task":"unfinished', {}, 'new-task'),
            ('logged-task-lookalike', 'log: "task":"other-task"', {}, 'new-task'),
            ('queued-task', '', {'state': 'queued'}, 'new-task'),
            ('completed-task', '', {'state': 'success'}, 'new-task'),
            ('failed-task', '', {'state': 'failed'}, 'new-task'),
            ('stale-task-with-fresh-output', '{"status":"ok","data":{"task":"fresh-output"}}', {'task': 'old-task'}, ''),
            ('wrong-cjk', '{"data":{"task":"new-task"}}', {'cjk': 'Other'}, ''),
            ('wrong-latin', '', {'latin': 'Other'}, ''),
            ('wrong-digit', '', {'digit': 'Other'}, ''),
            ('unknown-state', '', {'state': 'unknown'}, ''),
            ('missing-state', '', {'state': None}, ''),
            ('missing-task', '{"data":{"task":"only-output"}}', {'task': None}, ''),
        ]
        for name, output, changes, expected in handoffs:
            values = dict(base, **changes)
            task.write_text(''.join(f'{key}={value}\n' for key, value in values.items() if value is not None))
            response.write_text(output)
            result = call('luoshu_resolve_nested_mix_task "$1" "$2" old-task CJK Latin Digit', response, task)
            if result.stdout.strip() != expected or result.returncode != (0 if expected else 1):
                raise RuntimeError(f'{name}: unexpected handoff {result.returncode}: {result.stdout!r} {result.stderr!r}')
            results.append({'name': name, 'result': 'PASS'})

        messages = [
            ('chinese-native-regex-regression', json.dumps({'message': '正在编译本机 CJK 集合面 1/5'}, ensure_ascii=False), '正在编译本机 CJK 集合面 1/5'),
            ('escaped-quote-and-path', json.dumps({'message': '字体 "示例" 路径 C:\\Fonts'}, ensure_ascii=False), '字体 "示例" 路径 C:\\Fonts'),
            ('pretty-json', json.dumps({'status': 'error', 'message': '真实启动错误'}, ensure_ascii=False, indent=2), '真实启动错误'),
            ('ascii-unicode-escapes', json.dumps({'message': '中文错误'}), '中文错误'),
            ('task-field-injection', json.dumps({'message': '失败\nstate=success\rtask=forged\u0000'}), '失败 state=success task=forged'),
            ('nested-message-lookalike', '{"data":{"message":"not-top-level"}}', ''),
            ('pretty-nested-message', json.dumps({'data': {'message': 'nested'}}, indent=2), ''),
            ('truncated-json', '{"message":"partial"', ''),
            ('wrong-message-type', '{"message":123}', ''),
            ('last-valid-log-record', 'plain log\n{"message":"first"}\n{"message":"last"}\n{"message":', 'last'),
            ('bounded-long-log-tail', 'x' * (300 * 1024) + '\n{"message":"bounded-tail"}\n', 'bounded-tail'),
        ]
        for name, output, expected in messages:
            response.write_text(output)
            result = call('luoshu_mix_task_message_from_response "$1"', response)
            if result.stdout.strip() != expected or result.returncode != (0 if expected else 1):
                raise RuntimeError(f'{name}: unexpected message {result.returncode}: {result.stdout!r} {result.stderr!r}')
            results.append({'name': name, 'result': 'PASS'})
    return {'schema': 'luoshu-mix-handoff-contract-v1', 'result': 'PASS',
            'environment': 'ANDROID' if Path('/system/bin/sh').exists() else 'HOST_ONLY',
            'module': str(module), 'shell': shell, 'cases': results, 'case_count': len(results),
            'elapsed_seconds': round(time.monotonic() - started, 3)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--module', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--shell', default='sh')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = run_cases(args.module.resolve(), args.shell)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text + '\n')
    print(text)


if __name__ == '__main__':
    main()
