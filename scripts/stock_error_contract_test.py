#!/usr/bin/env python3
"""Portable current stock-scan error-function tests; not full scanner/mount proof."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import sys
import tempfile


def run(module, shell):
    android = Path('/system/bin/sh').exists()
    source = (module / 'common/font_manager.sh').read_text()
    escape = 'json_escape_router() {' + source.split('\njson_escape_router() {', 1)[1].split('\nstock_scan_available() {', 1)[0]
    function = 'stock_scan_json() {' + source.split('\nstock_scan_json() {', 1)[1].split('\nif [ "${1:-}" = action', 1)[0]
    message = '无法分析 "中文 字体.ttf"；请检查 C:\\data\\font 😀 $(printf injected) ${HOME} `pwd`'
    compact = lambda value: json.dumps(value, ensure_ascii=False, separators=(',', ':'))
    cases = [
        ('chinese-quotes-and-path', compact({'status': 'error', 'message': message}), 1, message, False, False),
        ('ascii-unicode-escapes', json.dumps({'message': message}), 1, message, False, False),
        ('pretty-top-level-message', json.dumps({'message': '正确', 'nested': {'message': '错误'}}, indent=2), 1, '正确', False, False),
        ('nested-message-lookalike', compact({'message': '正确', 'nested': {'message': '错误'}}), 1, '正确', False, False),
        ('nested-only-fallback', compact({'nested': {'message': '错误'}}), 1, compact({'nested': {'message': '错误'}}), False, False),
        ('last-valid-log-record', 'scan log\n{"message":"真正错误"}\n{"message":invalid}', 1, '真正错误', False, False),
        ('control-characters', compact({'message': '失败\r\nstate=success\x00\tmore'}), 1, '失败  state=success  more', False, False),
        ('plain-log-fallback', 'scan log\nplain failure\n', 1, 'scan log plain failure', False, False),
        ('unavailable-helper-fallback', 'plain failure', 1, 'plain failure', True, False),
        ('empty-default-error', '', 1, '原厂字体扫描失败', False, False),
        ('nonstring-message-fallback', '{"message":42}', 1, '{"message":42}', False, False),
        ('bounded-log-tail', 'x' * (300 * 1024) + '\nLUOSHU_STOCK_OUTPUT\n{"message":"末条错误"}', 1, '末条错误', False, False),
        ('success-stays-success', '{"status":"ok","slotCount":2}', 0, None, False, True),
        ('zero-exit-without-inventory-fails', '{"status":"ok","message":"missing inventory"}', 0, 'missing inventory', False, False),
    ]
    report = dict(schema='luoshu-stock-error-contract-v1', environment='ANDROID' if android else 'HOST_ONLY',
                  module=str(module), shell=shell, result='PASS', cases=[],
                  tested_scope='CURRENT_ERROR_ROUTER_FUNCTION_NOT_FULL_STOCK_SCAN')
    with tempfile.TemporaryDirectory(prefix='luoshu-stock-error-', dir='/data/local/tmp' if android else None) as temp:
        base = Path(temp); fixture = base / 'module'; common = fixture / 'common'; common.mkdir(parents=True)
        config = fixture / 'config'; config.mkdir()
        shutil.copyfile(module / 'common/task_scope.py', common / 'task_scope.py')
        data = base / 'scanner-output'; proxy = base / 'python-proxy'; script = base / 'error-function.sh'
        proxy.write_text('''#!/system/bin/sh
case "$1" in
    */task_scope.py)
        [ "$FIXTURE_HELPER_UNAVAILABLE" != true ] || exit 127
        if [ "$FIXTURE_ENVIRONMENT" = HOST_ONLY ]; then
            unset PYTHONHOME PYTHONPATH LD_LIBRARY_PATH
        fi
        exec "$FIXTURE_RUNTIME" "$@"
        ;;
    *)
        cat "$FIXTURE_OUTPUT"
        [ "$FIXTURE_INVENTORY" != true ] || printf '{"state":"ready"}\\n' > "$STOCK_INVENTORY"
        exit "$FIXTURE_CODE"
        ;;
esac
''')
        # The proxy is only a synthetic scanner. Helper requests still use the
        # original installed interpreter and byte-identical helper on Android.
        proxy.write_text(proxy.read_text().replace('#!/system/bin/sh', '#!' + shell))
        proxy.chmod(0o700)
        # Dash has a printf builtin; Android's original shell resolves printf
        # externally. Exercise the real kernel argv limit on HOST_ONLY too,
        # without replacing the Android shell or simulating E2BIG in a stub.
        external_printf = ''
        if not android:
            printf = shutil.which('printf')
            if printf is None:
                raise RuntimeError('External printf required for stock error host contract')
            external_printf = 'printf() { command ' + shlex.quote(printf) + ' "$@"; }\n'
        script.write_text(escape + function + external_printf + '''
stock_scan_available() { return 0; }
stock_scan_lock_acquire() { STOCK_SCAN_WAITED=false; return 0; }
stock_scan_lock_release() { return 0; }
stock_scan_json
''')
        runtime = module / 'common/python/bin/luoshu-python' if android else Path(sys.executable)
        env = dict(os.environ, MODDIR=str(fixture), STOCK_INVENTORY=str(config / 'inventory.json'),
                   PYROOT=str(module / 'common/python'), PYBIN=str(proxy), STOCK_SCANNER=str(base / 'scanner.py'),
                   FIXTURE_ENVIRONMENT=report['environment'], FIXTURE_RUNTIME=str(runtime), FIXTURE_OUTPUT=str(data))
        for name, text, code, expected, unavailable, inventory in cases:
            data.write_text(text)
            (config / 'inventory.json').unlink(missing_ok=True)
            result = subprocess.run([shell, str(script)], env=dict(env, FIXTURE_CODE=str(code),
                                    FIXTURE_HELPER_UNAVAILABLE=str(unavailable).lower(), FIXTURE_INVENTORY=str(inventory).lower()),
                                    capture_output=True, text=True, timeout=20)
            expected_code = 0 if inventory else 1
            value = json.loads(result.stdout)
            if (result.returncode != expected_code or result.stderr or
                    (inventory and value != {'status': 'ok', 'slotCount': 2}) or
                    (not inventory and value != {'status': 'error', 'message': expected})):
                raise RuntimeError(f'{name}: exit={result.returncode} output={value!r} stderr={result.stderr!r}; expected={expected!r}')
            report['cases'].append({'name': name, 'result': 'PASS'})
    report['case_count'] = len(report['cases'])
    report['helper_sha256'] = hashlib.sha256((module / 'common/task_scope.py').read_bytes()).hexdigest()
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--module', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--shell', default='/system/bin/sh' if Path('/system/bin/sh').exists() else '/bin/sh')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    value = json.dumps(run(args.module.resolve(), args.shell), ensure_ascii=False, separators=(',', ':')) + '\n'
    if args.output: args.output.write_text(value)
    print(value, end='')
