#!/usr/bin/env python3
"""Simulated slow/crashed workers through real mixed lifecycle controllers."""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'common'), str(ROOT / 'scripts')]
import universal_font_compiler as compiler
import universal_mixed_font as mixed
import universal_mixed_pipeline_test as fixture


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def poll(action, predicate, seconds=8):
    deadline = time.monotonic() + seconds
    value = None
    while time.monotonic() < deadline:
        try:
            value = action()
            if predicate(value):
                return value
        except (FileNotFoundError, ValueError):
            pass
        time.sleep(.08)
    raise AssertionError(f'timed out; last value: {value}')


class StallTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mixed-stall-')
        self.root = Path(self.temp.name)
        self.module = self.root / 'module'
        for name in ('common', 'config', 'cache', 'logs'):
            (self.module / name).mkdir(parents=True, exist_ok=True)
        self.env = dict(os.environ, MODDIR=str(self.module), MODULE_DIR=str(self.module),
                        LUOSHU_REAL_MODDIR=str(self.module), LUOSHU_MIX_REQUEST_ID='request-1',
                        LUOSHU_PYTHON=sys.executable, LUOSHU_MIX_WAIT_LOOPS='4')
        fixture.write_conf(self.module / 'config/mix-stage-next.conf', {'requestId': 'request-1'})

    def tearDown(self):
        helper = self.module / 'common/background_task.sh'
        if helper.exists():
            for name in ('axes_worker.pid', 'mix_worker.pid'):
                subprocess.run(['sh', '-c', '. "$MODDIR/common/background_task.sh"; luoshu_stop_task_pid "$MODDIR/config/$1"', 'cleanup', name],
                               env=self.env, capture_output=True, timeout=8)
        self.temp.cleanup()

    def copy(self, source: str, target: str | None = None):
        dest = self.module / (target or source)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / source, dest)

    def setup_nested(self, scenario: str, start: bool = True):
        self.copy('common/legacy_v14_4/v142_weighted_mix.sh', 'common/v142_weighted_mix.sh')
        self.copy('common/background_task.sh')
        self.copy('common/payload_commit_lock.sh')
        self.copy('common/mix_task_handoff.sh')
        write(self.module / 'common/util_functions.sh', '''detect_font_family() { printf '%s\\n' "${1%%-*}"; }
detect_font_weight() { printf 'regular\\n'; }
is_variable_font() { return 1; }
''')
        write(self.module / 'common/font_check.sh', '''font_validate() { FONT_CHECK_VARIABLE=false; FONT_CHECK_FORMAT=TTF; return 0; }
''')
        write(self.module / 'common/font_mix.sh', '''#!/bin/sh
. "$MODDIR/common/background_task.sh"
case "$1" in
 start)
   task=inner-task
   printf 'task=%s\\nstate=running\\nmessage=正在生成完整复合字体\\ncjk=%s\\nlatin=%s\\ndigit=%s\\n' "$task" "$2" "$3" "$4" > "$MODDIR/config/mix_task.conf"
   luoshu_start_detached "$MODDIR/config/mix_worker.pid" "$task" "$MODDIR/logs/inner.log" sh "$0" child "$task" || exit 1
   printf '{"status":"ok","data":{"task":"%s"}}\\n' "$task"
   ;;
 child)
   printf '{"percent":100}\\n' > "$MODDIR/config/composite_progress.json"
   case "$STALL_SCENARIO" in
    progress)
      printf 'requestId=%s\\npercent=86\\nmessage=通用引擎正在编译字体槽 3/9\\n' "$LUOSHU_MIX_REQUEST_ID" > "$MODDIR/config/universal-mixed-progress.conf"
      while [ ! -f "$MODDIR/release" ]; do sleep .1; done
      sed 's/state=running/state=success/' "$MODDIR/config/mix_task.conf" > "$MODDIR/config/mix_task.tmp"
      mv "$MODDIR/config/mix_task.tmp" "$MODDIR/config/mix_task.conf"
      ;;
    dead) exit 9 ;;
    cleaned-dead)
      printf '{"task":"%s","result":137,"leftoverPids":[]}\\n' "$2" > "$MODDIR/config/mix_worker.pid.cleanup.json"
      rm -f "$MODDIR/config/mix_worker.pid" "$MODDIR/config/mix_worker.pid.task" "$MODDIR/config/mix_worker.pid.boot"
      exit 9 ;;
    committed)
      mkdir -p "$MODDIR/.luoshu-payload-next"
      printf 'state=prepared\\nfont=mix\\nrequestId=%s\\n' "$LUOSHU_MIX_REQUEST_ID" > "$MODDIR/config/universal-font-next.conf"
      sleep 4
      ;;
    timeout) sleep 4; printf 'late' > "$MODDIR/late-commit" ;;
   esac
   ;;
esac
''')
        public = self.root / 'public'
        for name in ('CJK', 'Latin', 'Digit'):
            write(public / f'fonts/{name}-Regular.ttf', 'fixture-font')
        self.env.update(STALL_SCENARIO=scenario, LUOSHU_PUBLIC_DIR=str(public))
        if not start:
            return
        self.start_nested()

    def start_nested(self):
        started = subprocess.run(['sh', str(self.module / 'common/v142_weighted_mix.sh'), 'start',
                                  'CJK', 'Latin', 'Digit', 'wght=400', 'wght=400', 'wght=400'],
                                 env=self.env, capture_output=True, text=True, timeout=8)
        self.assertEqual(started.returncode, 0, started.stderr)
        self.assertEqual(json.loads(started.stdout)['status'], 'ok')

    def task(self):
        return mixed.conf(self.module / 'config/axes_task.conf')

    def test_complete_composition_exposes_current_compile_phase(self):
        self.setup_nested('progress')
        state = poll(self.task, lambda s: s.get('percent') == '86')
        self.assertEqual(state['state'], 'running')
        self.assertEqual(state['message'], '通用引擎正在编译字体槽 3/9')
        write(self.module / 'release', '')
        poll(self.task, lambda s: s.get('state') == 'success')

    def test_dead_nested_worker_fails_promptly(self):
        self.setup_nested('dead')
        state = poll(self.task, lambda s: s.get('state') == 'failed', 5)
        self.assertIn('子进程已退出', state['message'])
        self.assertEqual(mixed.conf(self.module / 'config/mix-stage-next.conf')['state'], 'cancelled')

    def test_cleaned_dead_nested_worker_fails_promptly(self):
        self.setup_nested('cleaned-dead')
        state = poll(self.task, lambda s: s.get('state') == 'failed', 5)
        self.assertIn('子进程已退出', state['message'])

    def test_parent_timeout_revokes_request_and_prevents_late_child_commit(self):
        self.env['LUOSHU_MIX_WAIT_LOOPS'] = '1'
        self.setup_nested('timeout')
        state = poll(self.task, lambda s: s.get('state') == 'failed', 6)
        self.assertIn('超时', state['message'])
        self.assertEqual(mixed.conf(self.module / 'config/mix-stage-next.conf')['state'], 'cancelled')
        time.sleep(2)
        self.assertFalse((self.module / 'late-commit').exists())

    def setup_real_timeout_fallback(self, start=True):
        from host_task_scope_fixture import install_task_scope
        self.setup_nested('progress', start=False)
        install_task_scope(self.module)
        self.copy('common/legacy_v14_4/font_mix_runtime.sh', 'common/font_mix.sh')
        self.copy('common/legacy_v14_4/mix_router.sh')
        self.copy('common/universal_font_cutover.sh')
        self.copy('common/universal_mixed_font.py')
        write(self.module / 'module.prop', 'id=LuoShu\n')
        for name in ('device_font_topology.json', 'device_font_roles.json'):
            write(self.module / 'config' / name, '{}')
        for name in ('universal_font_plan.sh', 'minimal_xml_router.sh', 'universal_font_compiler.sh',
                     'universal_font_cutover_gate.py', 'universal_font_deployment.py'):
            write(self.module / 'common' / name, '# not reached\n')
        write(self.module / 'common/universal_font_deployment.sh', '''case "$1" in
 prepare) sleep 30; printf late > "$MODDIR/late-prepare";;
 *) exit 99;;
esac
''')
        # Only font generation/ROM work is latency-injected. The axes worker,
        # nested async wrapper, scoped timeout, fallback, and finalizer mutex
        # are the production implementations; no fake successful finalizer.
        write(self.module / 'common/font_mix_engine.sh', '''#!/bin/sh
. "$MODDIR/common/background_task.sh"
case "$1" in
 start)
  printf 'task=inner-real\nstate=running\ncjk=%s\nlatin=%s\ndigit=%s\n' "$2" "$3" "$4" > "$MODDIR/config/mix_task.conf"
  luoshu_start_detached "$MODDIR/config/mix_worker.pid" inner-real "$MODDIR/logs/inner.log" sh "$0" child || exit 1
  printf '{"status":"ok","data":{"task":"inner-real"}}\n'
  ;;
 child)
  sh "$MODDIR/common/universal_font_cutover.sh" prepare-mixed LuoShuMix
  [ "$?" -ne 0 ] || exit 9
  grep -q 'reason=universal-prepare-timeout' "$MODDIR/config/universal-font-cutover.conf" || exit 8
  mkdir -p "$MODDIR/.luoshu-mix-stage/system/fonts"
  cp "$LUOSHU_PUBLIC_DIR/fonts/LuoShuMixCJK-Regular.ttf" "$MODDIR/.luoshu-mix-stage/system/fonts/Composite.ttf"
  printf 'requestId=request-1\ncjk=CJK\nlatin=Latin\ndigit=Digit\ncompositeHash=fixture\n' > "$MODDIR/.luoshu-mix-stage/.luoshu-mix-generation.conf"
  sed 's/state=running/state=success/' "$MODDIR/config/mix_task.conf" > "$MODDIR/config/mix_task.tmp"
  mv "$MODDIR/config/mix_task.tmp" "$MODDIR/config/mix_task.conf"
  ;;
esac
''')
        write(self.module / 'common/coloros_stage_complete.sh', '''#!/bin/sh
printf 'started\n' >> "$LUOSHU_REAL_MODDIR/rom-finalizers"
while [ ! -f "$LUOSHU_REAL_MODDIR/release-rom" ]; do sleep .1; done
printf complete > "$1/system/fonts/rom-complete"
''')
        fixture.write_conf(self.module / 'config/mix-stage-next.conf',
                           {'requestId': 'request-1', 'cjk': 'CJK', 'latin': 'Latin', 'digit': 'Digit'})
        write(self.module / '.luoshu-payload-next/sentinel', 'previous payload')
        write(self.module / 'config/font-payload-next.conf', 'state=prepared\nfont=previous\nrequestId=previous\n')
        self.bin = self.root / 'bin'; self.bin.mkdir()
        write(self.bin / 'getprop', '#!/bin/sh\ncase "$1" in ro.build.version.oplusrom) echo 16.1;; esac\n')
        (self.bin / 'getprop').chmod(0o755)
        shell = os.environ.get('LUOSHU_LOCK_TEST_SHELL') or shutil.which('mksh')
        if shell:
            (self.bin / 'sh').symlink_to(shell)
        native = os.environ.get('LUOSHU_LOCK_TEST_FLOCK') or shutil.which('toybox')
        if native:
            (self.bin / 'flock').symlink_to(native)
        self.env.update(PATH=str(self.bin)+':'+os.environ['PATH'], LUOSHU_SWITCH_ACTIVE_LABEL='mix', LUOSHU_MIX_PREPARE_TIMEOUT='0.2',
                        LUOSHU_PAYLOAD_LOCK_TIMEOUT='1', LUOSHU_MIX_WAIT_LOOPS='100')
        if start:
            self.start_nested()
            poll(lambda: (self.module / 'rom-finalizers').exists(), bool, 10)

    def test_real_axes_timeout_fallback_has_one_slow_finalizer(self):
        self.setup_real_timeout_fallback()
        # Exceed both the former 20-second mkdir lock and a scaled one-second
        # kernel contention budget. A unique owner has no contention timeout.
        time.sleep(22)
        self.assertEqual(self.task()['state'], 'running', self.task())
        self.assertEqual((self.module / 'rom-finalizers').read_text(), 'started\n')
        self.assertEqual((self.module / '.luoshu-payload-next/sentinel').read_text(), 'previous payload')
        write(self.module / 'release-rom', '')
        state = poll(self.task, lambda s: s.get('state') in ('success', 'failed'), 8)
        self.assertEqual(state['state'], 'success', state)
        self.assertEqual(mixed.conf(self.module / 'config/font-payload-next.conf')['requestId'], 'request-1')
        self.assertTrue((self.module / '.luoshu-payload-next/system/fonts/rom-complete').exists())
        self.assertFalse((self.module / 'late-prepare').exists())
        report = poll(lambda: json.loads((self.module / 'config/axes_worker.pid.cleanup.json').read_text()),
                      lambda r: r.get('leftoverPids') == [])
        self.assertEqual(report['result'], 0)

    def test_direct_fixed_mix_keeps_its_monitor_finalizer(self):
        self.setup_real_timeout_fallback(start=False)
        public = self.root / 'public/fonts'
        shutil.copyfile(public / 'CJK-Regular.ttf', public / 'LuoShuMixCJK-Regular.ttf')
        result = subprocess.run(['sh', str(self.module / 'common/font_mix.sh'), 'start', 'CJK', 'Latin', 'Digit'],
                                env=self.env, capture_output=True, text=True, timeout=8)
        self.assertEqual(result.returncode, 0, result.stderr)
        poll(lambda: (self.module / 'rom-finalizers').exists(), bool, 10)
        write(self.module / 'release-rom', '')
        state = poll(lambda: mixed.conf(self.module / 'config/mix-finalize-state.conf'),
                     lambda r: r.get('state') in ('success', 'failed'), 8)
        self.assertEqual(state['state'], 'success')
        self.assertEqual(state['requestId'], 'request-1')
        self.assertEqual((self.module / 'rom-finalizers').read_text(), 'started\n')
        self.assertTrue((self.module / '.luoshu-payload-next/system/fonts/rom-complete').exists())

    def test_real_axes_cancel_during_rom_completion_preserves_previous_payload(self):
        self.setup_real_timeout_fallback()
        result = subprocess.run(['sh', '-c', '. "$MODDIR/common/background_task.sh"; luoshu_stop_task_pid "$MODDIR/config/axes_worker.pid"'],
                                env=self.env, capture_output=True, text=True, timeout=8)
        self.assertEqual(result.returncode, 0, result.stderr)
        write(self.module / 'release-rom', '')
        time.sleep(.5)
        self.assertEqual((self.module / '.luoshu-payload-next/sentinel').read_text(), 'previous payload')
        self.assertEqual(mixed.conf(self.module / 'config/font-payload-next.conf')['requestId'], 'previous')
        self.assertFalse((self.module / '.luoshu-payload-next/system/fonts/rom-complete').exists())
        report = json.loads((self.module / 'config/axes_worker.pid.cleanup.json').read_text())
        self.assertEqual(report['leftoverPids'], [])
        self.assertNotEqual(report['result'], 0)

    def test_scoped_parent_waits_for_slow_finalizer_before_success(self):
        from host_task_scope_fixture import install_task_scope
        install_task_scope(self.module)
        write(self.module / 'common/legacy_v14_4/mix_router.sh', """#!/bin/sh
[ "$1" = finalize ] || exit 2
printf started > "$MODDIR/finalizer-started"
while [ ! -f "$MODDIR/finalizer-release" ]; do sleep .1; done
mkdir -p "$MODDIR/.luoshu-payload-next"
printf committed > "$MODDIR/.luoshu-payload-next/sentinel"
""")
        self.setup_nested('progress')
        poll(self.task, lambda s: s.get('percent') == '86')
        write(self.module / 'release', '')
        poll(lambda: (self.module / 'finalizer-started').exists(), bool)
        state = self.task()
        self.assertEqual(state['state'], 'running')
        self.assertEqual(state['percent'], '97')
        self.assertFalse((self.module / '.luoshu-payload-next/sentinel').exists())
        write(self.module / 'finalizer-release', '')
        poll(self.task, lambda s: s.get('state') == 'success')
        self.assertEqual((self.module / '.luoshu-payload-next/sentinel').read_text(), 'committed')
        cleanup = poll(lambda: json.loads((self.module / 'config/axes_worker.pid.cleanup.json').read_text()),
                       lambda r: r.get('leftoverPids') == [])
        self.assertEqual(cleanup['result'], 0)

    def test_committed_generation_wins_deadline_race(self):
        self.env['LUOSHU_MIX_WAIT_LOOPS'] = '1'
        self.setup_nested('committed')
        state = poll(self.task, lambda s: s.get('state') in ('failed', 'success'), 6)
        self.assertEqual(state['state'], 'success', state)
        self.assertNotEqual(mixed.conf(self.module / 'config/mix-stage-next.conf').get('state'), 'cancelled')
        self.assertEqual(mixed.conf(self.module / 'config/universal-font-next.conf')['requestId'], 'request-1')

    def test_scoped_prepare_deadline_preserves_previous_payload(self):
        self.copy('common/universal_font_cutover.sh')
        self.copy('common/universal_mixed_font.py')
        self.copy('common/task_scope.py')
        for filename in ('device_font_topology.json', 'device_font_roles.json'):
            write(self.module / 'config' / filename, '{}')
        for filename in ('universal_font_plan.sh', 'minimal_xml_router.sh', 'universal_font_compiler.sh',
                         'universal_font_cutover_gate.py', 'universal_font_deployment.py'):
            write(self.module / 'common' / filename, '# should never be reached\n')
        write(self.module / 'common/universal_font_deployment.sh', '''#!/bin/sh
case "$1" in
 prepare)
   ( sleep 1.5; printf late > "$MODDIR/late-prepare" ) &
   sleep 30
   ;;
 *) printf wrong > "$MODDIR/stage-was-called" ;;
esac
''')
        previous = self.module / 'config/universal-font-next.conf'
        write(previous, 'font=previous\ndeploymentId=previous-id\n')
        sentinel = self.module / '.luoshu-payload-next/sentinel'
        write(sentinel, 'previous payload')
        env = dict(self.env, LUOSHU_SWITCH_ACTIVE_LABEL='mix', LUOSHU_MIX_PREPARE_TIMEOUT='0.2')
        began = time.monotonic()
        result = subprocess.run(['sh', str(self.module / 'common/universal_font_cutover.sh'), 'prepare-mixed', 'LuoShuMix'],
                                env=env, capture_output=True, text=True, timeout=6)
        self.assertNotEqual(result.returncode, 0)
        self.assertLess(time.monotonic() - began, 5)
        self.assertEqual(mixed.conf(self.module / 'config/universal-font-cutover.conf')['reason'], 'universal-prepare-timeout')
        time.sleep(1.7)
        self.assertFalse((self.module / 'late-prepare').exists())
        self.assertFalse((self.module / 'stage-was-called').exists())
        self.assertEqual(sentinel.read_text(), 'previous payload')
        self.assertEqual(previous.read_text(), 'font=previous\ndeploymentId=previous-id\n')

    def test_stale_finalizer_cannot_commit_newer_generation(self):
        self.copy('common/legacy_v14_4/mix_router.sh')
        self.copy('common/payload_commit_lock.sh')
        fixture.write_conf(self.module / 'config/mix-stage-next.conf',
                           {'requestId': 'newer-request', 'cjk': 'CJK', 'latin': 'Latin', 'digit': 'Digit'})
        fixture.write_conf(self.module / '.luoshu-mix-stage/.luoshu-mix-generation.conf',
                           {'requestId': 'newer-request', 'cjk': 'CJK', 'latin': 'Latin', 'digit': 'Digit', 'compositeHash': 'new'})
        write(self.module / '.luoshu-mix-stage/system/fonts/next.ttf', 'newer font')
        write(self.module / '.luoshu-payload-next/sentinel', 'previous payload')
        result = subprocess.run(['sh', str(self.module / 'common/legacy_v14_4/mix_router.sh'), 'finalize'],
                                env=self.env, capture_output=True, text=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.module / '.luoshu-payload-next/sentinel').read_text(), 'previous payload')
        self.assertTrue((self.module / '.luoshu-mix-stage/system/fonts/next.ttf').exists())

    def test_cancelled_request_cannot_finalize(self):
        self.copy('common/legacy_v14_4/mix_router.sh')
        fixture.write_conf(self.module / 'config/mix-stage-next.conf', {'requestId': 'request-1', 'state': 'cancelled'})
        write(self.module / '.luoshu-mix-stage/system/fonts/fake.ttf', 'not-to-be-staged')
        write(self.module / '.luoshu-payload-next/sentinel', 'previous payload')
        result = subprocess.run(['sh', str(self.module / 'common/legacy_v14_4/mix_router.sh'), 'finalize'],
                                env=self.env, capture_output=True, text=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.module / '.luoshu-payload-next/sentinel').read_text(), 'previous payload')
        self.assertFalse((self.module / 'config/font-payload-next.conf').exists())
        with self.assertRaisesRegex(ValueError, 'superseded|cancelled'):
            mixed.current(self.module, 'request-1')

    def test_late_cancelled_stage_never_activates_after_new_request(self):
        self.copy('common/universal_next_boot.sh')
        write(self.module / 'config/mix-cancelled-requests/request-1', 'cancelled\n')
        fixture.write_conf(self.module / 'config/mix-stage-next.conf', {'requestId': 'newer-request'})
        fixture.write_conf(self.module / 'config/universal-font-next.conf',
                           {'state': 'prepared', 'font': 'mix', 'requestId': 'request-1',
                            'deploymentId': 'late-id', 'payloadDigest': 'late-digest', 'previousFont': 'Live A'})
        write(self.module / '.luoshu-payload-next/sentinel', 'cancelled late payload')
        write(self.module / '.luoshu-payload/sentinel', 'previous live payload')
        write(self.module / 'config/active_font.conf', 'mix\n')
        result = subprocess.run(['sh', '-c', '. "$MODDIR/common/universal_next_boot.sh"; universal_font_next_boot_activate'],
                                env=self.env, text=True, capture_output=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.module / '.luoshu-payload/sentinel').read_text(), 'previous live payload')
        self.assertFalse((self.module / '.luoshu-payload-next').exists())
        self.assertFalse((self.module / 'config/universal-font-next.conf').exists())
        self.assertEqual((self.module / 'config/active_font.conf').read_text().strip(), 'Live A')
        self.assertEqual(mixed.conf(self.module / 'config/universal-font-next.failed.conf')['reason'], 'composite-request-cancelled')
        self.assertEqual(mixed.current(self.module, 'newer-request')['requestId'], 'newer-request')

    def test_blocked_nonroutable_plan_does_zero_compiles(self):
        import universal_font_compiler_test as basic_fixture
        source, stock = self.root / 'ascii.ttf', self.root / 'stock.ttf'
        basic_fixture.make_font(source, family='Latin Only')
        fixture.make_font(stock)
        stocks = {'/system/fonts/Latin.ttf': stock, '/system/fonts/CJK.ttf': stock}
        plan, route = fixture.plans(source, stocks, {'/system/fonts/Latin.ttf': 'latin', '/system/fonts/CJK.ttf': 'cjk'})
        self.assertEqual(plan['targets']['/system/fonts/CJK.ttf']['action'], 'blocked')
        with patch.dict(os.environ, LUOSHU_UNIVERSAL_MIX_STRICT='1'), patch.object(compiler, '_compile_unit') as compile_unit:
            with self.assertRaisesRegex(compiler.CompilerError, 'mixed-preflight.*blocked'):
                compiler.compile_all(plan, route, stocks, self.root / 'out', False)
            compile_unit.assert_not_called()

    def test_stale_compile_phase_does_not_hide_finalizer_progress(self):
        self.copy('common/legacy_v14_4/mix_router.sh')
        fixture.write_conf(self.module / 'config/axes_task.conf',
                           {'task': 'outer-task', 'state': 'running', 'percent': 97, 'message': '正在提交下一启动字体负载'})
        fixture.write_conf(self.module / 'config/universal-mixed-progress.conf',
                           {'requestId': 'request-1', 'percent': 82, 'message': '通用引擎正在编译字体槽 1/8'})
        result = subprocess.run(['sh', str(self.module / 'common/legacy_v14_4/mix_router.sh'), 'status', 'outer-task'],
                                env=self.env, capture_output=True, text=True, timeout=5)
        data = json.loads(result.stdout)['data']
        self.assertEqual(data['progress']['percent'], 97)
        self.assertEqual(data['message'], '正在提交下一启动字体负载')

    def test_impossible_atomic_plan_does_zero_compiles(self):
        source, stock, vf = [self.root / name for name in ('source.ttf', 'stock.ttf', 'vf.ttf')]
        fixture.make_font(source, marked=True)
        fixture.make_font(stock)
        fixture.make_font(vf, variable=True)
        stocks = {'/system/fonts/Regular.ttf': stock, '/system/fonts/MiSansVF.ttf': vf}
        plan, route = fixture.plans(source, stocks, {p: 'ui-sans' for p in stocks})
        with patch.dict(os.environ, LUOSHU_UNIVERSAL_MIX_STRICT='1'), patch.object(compiler, '_compile_unit') as compile_unit:
            with self.assertRaisesRegex(compiler.CompilerError, 'mixed-preflight.*physical variable'):
                compiler.compile_all(plan, route, stocks, self.root / 'out', False)
            compile_unit.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
