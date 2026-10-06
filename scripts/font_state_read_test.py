#!/usr/bin/env python3
"""Real mksh/dash state-reader parity and bounded hot-path benchmark.

Only isolated files and extracted production functions are used. Timings are
host fixture timings, not a claim about complete Android font-switch latency.
Usage: python3 scripts/font_state_read_test.py [repository_or_package_root]
       python3 scripts/font_state_read_test.py --benchmark
"""
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import unittest

BENCHMARK = '--benchmark' in sys.argv
if BENCHMARK:
    sys.argv.remove('--benchmark')
ROOT = (Path(sys.argv.pop(1)).resolve()
        if len(sys.argv) > 1 and not sys.argv[1].startswith('-')
        else Path(__file__).resolve().parents[1])
MKSH = os.environ.get('LUOSHU_TEST_MKSH') or shutil.which('mksh')
DASH = shutil.which('dash')
if not MKSH or not DASH:
    raise SystemExit('Real mksh and dash are required (LUOSHU_TEST_MKSH may select mksh).')
SHELLS = [('mksh', MKSH), ('dash', DASH)]
READERS = ['common/font_switch_task.sh', 'common/legacy_v14_4/mix_router.sh']
BASELINE = """read_value() {
    sed -n "s/^${2}=//p" "$1" 2>/dev/null | head -n1 | tr -d '\\r\\n'
}
"""


def function(path, name):
    source = path.read_text()
    start = source.index(name + '() {\n')
    return source[start:source.index('\n}', start) + 2] + '\n'


def reader(path):
    result = function(ROOT / path, 'read_value')
    if path.endswith('font_switch_task.sh'):
        result = result.replace('read_value() {', 'single_read_value() {', 1)
        result += 'read_value() { TASK_FILE="$1"; single_read_value "$2"; }\n'
    return result


def run(shell, script, *args):
    return subprocess.run([shell, '-c', script, 'fixture', *map(str, args)],
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          timeout=30, check=True).stdout


class StateReadTests(unittest.TestCase):
    def test_real_shells(self):
        self.assertIn(b'MIRBSD KSH', run(MKSH, 'printf "%s" "$KSH_VERSION"'))
        self.assertNotEqual(Path(MKSH).resolve(), Path(DASH).resolve())

    def test_all_value_and_missing_cases_match_previous_reader(self):
        cases = [
            b'', b'font=\n', b'font=last line', b'font=first\nfont=second\n',
            b'prefixfont=no\nfont= yes \\ \\n = next\n',
            b'font=\rfirst\rmiddle\rlast\r\n', b'font=-n\n',
            b'font=\tleft\x01middle\rright\t\n',
            'font=洛书 混合字体 𠀀\n'.encode(),
            b'font=$(touch SHOULD_NOT_EXIST); `echo unsafe` ${HOME} * ? [x]\n',
            b'ignored=1\nfont=\"quoted\" /path/a=b/c | x & y\n',
            b'font\r=not-a-key\nfont=correct\n',
            b' font=not-a-key\nfont =not-a-key\n',
            b'font=' + b'x' * 16384 + b'\n',
        ]
        with tempfile.TemporaryDirectory(prefix='luoshu-state-read-') as directory:
            root = Path(directory)
            path = root / 'state with spaces.conf'
            for shell_name, shell in SHELLS:
                for content in cases:
                    path.write_bytes(content)
                    expected = run(shell, BASELINE + 'read_value "$1" font', path)
                    for source in READERS:
                        with self.subTest(shell=shell_name, source=source, content=content[:80]):
                            actual = run(shell, reader(source) + 'read_value "$1" font', path)
                            self.assertEqual(actual, expected)
                for missing in (root / 'absent.conf', root):
                    for source in READERS:
                        with self.subTest(shell=shell_name, source=source, missing=missing):
                            self.assertEqual(run(shell, reader(source) + 'read_value "$1" font', missing), b'')
                self.assertFalse((root / 'SHOULD_NOT_EXIST').exists())

    def test_state_files_are_never_executed_and_keys_are_literal(self):
        with tempfile.TemporaryDirectory(prefix='luoshu-state-key-') as directory:
            path = Path(directory) / 'state.conf'
            marker = Path(directory) / 'executed'
            path.write_text(f'font=$(touch "{marker}")\nfont.name=literal\nfontXname=wrong\n')
            for _, shell in SHELLS:
                for source in READERS:
                    script = reader(source)
                    self.assertEqual(run(shell, script + 'read_value "$1" font.name', path), b'literal')
                    self.assertEqual(run(shell, script + 'read_value "$1" absent', path), b'')
                    run(shell, script + 'read_value "$1" font', path)
                    self.assertFalse(marker.exists())

    def test_reader_does_not_launch_external_commands(self):
        # No sed/head/tr or other executable is available on this PATH. Shell
        # builtins must still parse every field and embedded carriage return.
        with tempfile.TemporaryDirectory(prefix='luoshu-state-builtins-') as directory:
            path = Path(directory) / 'state.conf'
            path.write_bytes(b'task=t1\nfont=Lo\rShu\nstate=success\n')
            for _, shell in SHELLS:
                for source in READERS:
                    output = run(shell, reader(source) + '''
saved_path=$PATH; PATH="$2"
a=$(read_value "$1" task); b=$(read_value "$1" font); c=$(read_value "$1" state)
PATH=$saved_path
printf '<%s>\n' "$a" "$b" "$c"
''', path, directory)
                    self.assertEqual(output, b'<t1>\n<LoShu>\n<success>\n')

    def test_config_endpoint_matches_baseline(self):
        router = ROOT / READERS[1]
        suffix = function(router, 'json_escape_router') + function(router, 'mix_config_json_fast')
        suffix += '\nREALMOD="$1"; ACTIVE_CONF="$1/config/active_font.conf"; mix_config_json_fast\n'
        with tempfile.TemporaryDirectory(prefix='luoshu-state-config-') as directory:
            config = Path(directory) / 'config'
            config.mkdir()
            (config / 'active_font.conf').write_text('mix\n')
            for value in ('', 'cjk=中文\nlatin=Latin\ndigit=数字\n',
                          'cjk=字 "体"\\名\ncjkWeight=700\nlatinWeight=bad\n'
                          'digitWeight=100\ncjkAxes=wght=700,wdth=90\n'):
                (config / 'axes_mix.conf').write_text(value)
                for _, shell in SHELLS:
                    expected = run(shell, BASELINE + suffix, directory)
                    actual = run(shell, reader(READERS[1]) + suffix, directory)
                    self.assertEqual(actual, expected)
                    self.assertEqual(json.loads(actual)['status'], 'ok')


def benchmark():
    # 20 fields, including late/missing lookups: 200 reads per sample. Compare
    # alternating old/new samples to reduce process/load-order bias.
    fields = ['task', 'state', 'font', 'message', 'started', 'finished', 'pid',
              'heartbeat', 'timeout', 'elapsed', 'percent', 'bootId', 'reused',
              'terminalState', 'terminalMessage', 'cleanupConfirmed', 'liveApplied',
              'activation', 'requestId', 'absent']
    loop = '''
file="$1"; n=0
while [ "$n" -lt 10 ]; do
  for key in ''' + ' '.join(fields) + '''; do
    value=$(read_value "$file" "$key")
  done
  n=$((n + 1))
done
'''
    with tempfile.TemporaryDirectory(prefix='luoshu-state-bench-') as directory:
        path = Path(directory) / 'state.conf'
        path.write_text(''.join(f'{field}=fixture-{field}\n' for field in fields[:-1]))
        for name, shell in SHELLS:
            samples = {'before': [], 'after': []}
            scripts = {'before': BASELINE + loop, 'after': reader(READERS[1]) + loop}
            for iteration in range(6):
                for label in (('before', 'after') if iteration % 2 == 0 else ('after', 'before')):
                    started = time.perf_counter()
                    run(shell, scripts[label], path)
                    samples[label].append(time.perf_counter() - started)
            medians = {label: statistics.median(values) for label, values in samples.items()}
            print(json.dumps({'shell': name, 'readsPerSample': 200,
                              'fixture': '19-line task state; 20 queried keys; 10 rounds',
                              'samplesSeconds': samples, 'medianSeconds': medians,
                              'speedup': medians['before'] / medians['after'],
                              'externalCommandsPerSample': {'before': 600, 'after': 0},
                              'scope': 'isolated host state-reader, not full phone switch'}, sort_keys=True))

        config = Path(directory) / 'config'
        config.mkdir()
        (config / 'active_font.conf').write_text('mix\n')
        (config / 'axes_mix.conf').write_text(
            'cjk=中文\nlatin=Latin\ndigit=Digits\ncjkAxes=wght=700\n'
            'latinAxes=wght=400\ndigitAxes=wght=500\ncjkWeight=700\n'
            'latinWeight=400\ndigitWeight=500\n')
        router = ROOT / READERS[1]
        handler = function(router, 'json_escape_router') + function(router, 'mix_config_json_fast')
        handler += '''
REALMOD="$1"; ACTIVE_CONF="$1/config/active_font.conf"; n=0
while [ "$n" -lt 10 ]; do
    mix_config_json_fast >/dev/null
    n=$((n + 1))
done
'''
        for name, shell in SHELLS:
            samples = {'before': [], 'after': []}
            scripts = {'before': BASELINE + handler, 'after': reader(READERS[1]) + handler}
            for iteration in range(6):
                for label in (('before', 'after') if iteration % 2 == 0 else ('after', 'before')):
                    started = time.perf_counter()
                    run(shell, scripts[label], directory)
                    samples[label].append(time.perf_counter() - started)
            medians = {label: statistics.median(values) for label, values in samples.items()}
            print(json.dumps({'shell': name, 'callsPerSample': 10,
                              'fixture': 'production mix_config_json_fast with isolated persisted selection',
                              'samplesSeconds': samples, 'medianSeconds': medians,
                              'speedup': medians['before'] / medians['after'],
                              'scope': 'host config-response handler; startup/root bridge excluded; not full phone switch'}, sort_keys=True))


if __name__ == '__main__':
    if BENCHMARK:
        benchmark()
    else:
        unittest.main()
