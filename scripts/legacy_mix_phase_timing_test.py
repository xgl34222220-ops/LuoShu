#!/usr/bin/env python3
"""Actual legacy font drivers emit bounded, request-associated phase evidence."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
from fontTools.ttLib import TTFont

import legacy_mix_fixed_cache_identity_test as fixed_fixture
from legacy_mix_fixed_cache_identity_test import digest, values
import legacy_mix_fixed_prepare_reuse_test as auto_fixture

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'common'))
import font_layout_diagnostic as diagnostic


def events(module):
    path = module / 'logs/fontswitch.log'
    return [dict(word.split('=', 1) for word in line.split()[1:])
            for line in path.read_text().splitlines() if line.startswith('[MIX-PHASE] ')] if path.is_file() else []


class LegacyMixPhaseTiming(unittest.TestCase):
    setUp = fixed_fixture.FixedCompositeCacheIdentity.setUp
    cancel_owned_scopes = fixed_fixture.FixedCompositeCacheIdentity.cancel_owned_scopes
    count = fixed_fixture.FixedCompositeCacheIdentity.count
    build = fixed_fixture.FixedCompositeCacheIdentity.build
    good = fixed_fixture.FixedCompositeCacheIdentity.good

    def enable(self):
        self.env.update(LUOSHU_MIX_REQUEST_ID='mix-request-1800000000-123',
                        LUOSHU_MIX_PHASE_OUTER_TASK='axes-1800000000-123',
                        LUOSHU_TASK_SCOPE_TASK='mix-1800000000-124.apply')

    def completed(self, phase, records=None):
        return [item for item in records or events(self.module)
                if item['phase'] == phase and item['event'] == 'end']

    def router_complete(self, config_name):
        router = self.module / 'common/legacy_v14_4/mix_router.sh'
        start = subprocess.run(['sh', str(router), 'start', 'CJK', 'Latin', 'Digit',
                                'wght=400', 'wght=400', 'wght=400'],
                               env=self.env, capture_output=True, text=True, timeout=20)
        self.assertEqual(start.returncode, 0, start.stdout + start.stderr)
        response = json.loads(start.stdout)
        self.assertEqual(response['status'], 'ok', response)
        task = response['data']['task']
        deadline = time.monotonic() + 35
        config = {}
        while time.monotonic() < deadline:
            config = values(self.module / 'config' / config_name)
            if (config.get('task') == task and config.get('state') in ('success', 'failed')
                    and not list((self.module / '.luoshu-state/tasks').glob('*.owner.json'))):
                break
            time.sleep(.04)
        self.assertEqual(config.get('task'), task)
        self.assertEqual(config.get('state'), 'success', config)
        status = subprocess.run(['sh', str(router), 'status', task], env=self.env,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(status.returncode, 0, status.stdout + status.stderr)
        terminal = json.loads(status.stdout)
        self.assertEqual(terminal['data']['task'], response['data']['task'])
        self.assertEqual(terminal['data']['state'], 'success')
        self.assertEqual(terminal['data']['liveApplied'], False)
        return config, response, terminal

    def evidence(self, name, timing, response, terminal, next_font):
        directory = os.environ.get('LUOSHU_PHASE_EVIDENCE_DIR')
        if directory:
            target = Path(directory)
            target.mkdir(parents=True, exist_ok=True)
            (target / (name + '.json')).write_text(json.dumps({
                'scope': 'host-real-font-driver-generic-next-transaction',
                'appObservationCollected': False, 'oemDeviceCollected': False,
                'startTaskField': 'data.task', 'terminalTaskField': 'data.task',
                'exactTaskPair': response['data']['task'] == terminal['data']['task'],
                'terminalState': terminal['data']['state'],
                'nextFont': values(self.module / 'config/font-payload-next.conf').get('font'),
                'commitRequestMatches': (values(self.module / 'config/mix-commit.conf').get('requestId')
                                         == values(self.module / 'config/axes_task.conf').get('requestId')),
                'liveApplied': terminal['data']['liveApplied'],
                'fontSha256': digest(next_font), 'generatorCalls': self.count(self.calls),
                'timing': timing,
            }, ensure_ascii=False, indent=2) + '\n')

    def test_real_cold_warm_keeps_bytes_progress_and_four_line_proof(self):
        self.enable()
        cold, font = self.good()
        original = font.read_bytes()
        cold_events = events(self.module)
        for phase in ('cache_lookup', 'cold_composite_runner', 'validate', 'cache_publish'):
            self.assertTrue(self.completed(phase, cold_events), (phase, cold_events))
        receipt = Path(str(font) + '.receipt')
        self.assertEqual(len(receipt.read_text().splitlines()), 4)
        self.assertEqual(values(receipt)['schema'], 'fixed-composite-receipt-v1')
        progress = json.loads((self.module / 'config/composite_progress.json').read_text())
        self.assertEqual(progress['stage'], 'done')
        warm, reused = self.good()
        self.assertEqual(warm.data['cacheHit'], 'true')
        self.assertEqual(reused.read_bytes(), original)
        self.assertEqual((self.count(self.calls), self.count(self.validations)), (1, 1))
        warm_events = events(self.module)[len(cold_events):]
        self.assertEqual([v['phase'] for v in warm_events if v['event'] == 'end'], ['cache_lookup'])
        self.assertEqual(warm_events[-1]['method'], 'receipt-hit')
        self.assertEqual(json.loads((self.module / 'config/composite_progress.json').read_text())['stage'], 'cache')
        for item in cold_events + warm_events:
            self.assertEqual(item['request'], self.env['LUOSHU_MIX_REQUEST_ID'])
            self.assertEqual(item['outer'], self.env['LUOSHU_MIX_PHASE_OUTER_TASK'])
            self.assertEqual(item['clock'], 'proc-uptime')
            if item['event'] == 'end':
                self.assertGreaterEqual(int(item['elapsedMs']), 0)
        self.assertNotIn(str(self.public), json.dumps(cold_events + warm_events))

    def test_real_validator_failure_reports_original_failure(self):
        self.enable()
        result = self.build(extra_env={'FIXED_DAMAGE_OUTPUT': '1'})
        self.assertNotEqual(result.returncode, 0)
        self.assertTrue(self.completed('validate'))
        self.assertEqual(self.completed('validate')[-1]['result'], 'failed')
        self.assertFalse(list(self.cache.glob('*.otf')))
        self.assertEqual(list(self.scope_tmp.iterdir()), [])

    def test_real_generation_identity_race_reports_publish_failure(self):
        self.enable()
        changed = self.module / 'common/composite_layout.py'
        result = self.build(extra_env={'FIXED_MUTATE_AFTER_GEN': str(changed)})
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.completed('cold_composite_runner')[-1]['result'], 'ok')
        self.assertEqual(self.completed('cache_publish')[-1]['result'], 'failed')
        self.assertFalse(list(self.cache.glob('*.otf')))
        self.assertEqual(list(self.scope_tmp.iterdir()), [])

    def test_real_router_prepare_mapper_next_finalize_and_receipt(self):
        _, cached = self.good()
        original = cached.read_bytes()
        cached.write_bytes(b'damaged-cache-block' * 456)
        task, response, terminal = self.router_complete('axes_task.conf')
        self.assertEqual(self.count(self.calls), 2)
        next_font = self.module / '.luoshu-payload-next/system/fonts/Roboto-Regular.ttf'
        self.assertEqual(next_font.read_bytes(), original)
        with TTFont(next_font, recalcTimestamp=False) as font:
            self.assertTrue(set(map(ord, 'Aa09中文')).issubset(font.getBestCmap()))
        self.assertEqual(values(self.module / 'config/mix-commit.conf')['requestId'], task['requestId'])
        self.assertEqual(values(self.module / 'config/font-payload-next.conf')['font'], 'mix')
        records = events(self.module)
        request = task['requestId']
        records = [v for v in records if v['request'] == request]
        self.assertTrue(records)
        self.assertEqual({v['outer'] for v in records}, {task['task']})
        for phase in ('prepare', 'child_start', 'wait_child_cleanup', 'worker_finalize',
                      'map_payload', 'finalize_lock', 'next_commit', 'live_mount'):
            self.assertTrue(self.completed(phase, records), (phase, records))
        timing = diagnostic.collect_mix_timings(self.module)
        self.assertEqual(timing['requests'][-1]['backendTotal']['status'], 'available', timing)
        self.assertTrue(timing['requests'][-1]['backendTotal']['cleaned'])
        self.assertEqual(timing['requests'][-1]['safeSwitch']['status'], 'unavailable')
        self.evidence('fixed-real-timing', timing, response, terminal, next_font)
        serialized = json.dumps(timing)
        for secret in (request, task['task'], str(self.module), str(self.public), '/proc/', 'bootId'):
            self.assertNotIn(secret, serialized)

    def test_real_auto_router_reuses_safe_clock_and_exact_task_pair(self):
        # SAFE clones a real current payload; the fixed-only fixture never
        # needed that tree because its compatibility engine stages separately.
        (self.module / '.luoshu-payload/system/fonts').mkdir(parents=True)
        auto_fixture.variable_font(self.sources[0])
        task, response, terminal = self.router_complete('axes_task.conf')
        self.assertTrue(response['data']['task'].startswith('auto-mix-'))
        self.assertEqual(self.count(self.calls), 9)
        next_font = self.module / '.luoshu-payload-next/system/fonts/Roboto-Regular.ttf'
        with TTFont(next_font, recalcTimestamp=False) as font:
            self.assertTrue(set(map(ord, 'Aa09中文')).issubset(font.getBestCmap()))
            self.assertNotIn('fvar', font)
        self.assertEqual(values(self.module / 'config/mix-commit.conf')['requestId'], task['requestId'])
        records = [item for item in events(self.module) if item['request'] == task['requestId']]
        runners = self.completed('cold_composite_runner', records)
        self.assertEqual({item['weight'] for item in runners}, {str(n) for n in range(100, 901, 100)})
        self.assertEqual(len(runners), 9)
        self.assertEqual(self.completed('worker_finalize', records)[-1]['weight'], 'fixed')
        timing = diagnostic.collect_mix_timings(self.module)
        latest = timing['requests'][-1]
        self.assertEqual(latest['backendTotal']['status'], 'available', timing)
        self.assertTrue(latest['backendTotal']['cleaned'])
        self.assertEqual(self.completed('safe_apply', records)[-1]['result'], 'ok')
        self.assertEqual(latest['safeSwitch']['status'], 'unavailable', timing)
        self.assertEqual(latest['safeSwitch']['reason'], 'identity-not-associated')
        safe_lines = [line for line in (self.module / 'logs/fontswitch.log').read_text().splitlines()
                      if line.startswith('[SAFE-TIMING] ')]
        self.assertTrue(any('phase=map_rom ' in line for line in safe_lines))
        self.assertTrue(any('event=total ' in line for line in safe_lines))
        self.assertTrue(all('task=safe-switch-' in line for line in safe_lines))
        self.assertFalse(any(item['phase'] in ('complete_hyperos', 'complete_coloros') for item in latest['phases']))
        self.evidence('auto-real-timing', timing, response, terminal, next_font)
        for secret in (task['requestId'], task['task'], str(self.module), str(self.public)):
            self.assertNotIn(secret, json.dumps(timing))

    def test_actual_scope_timeout_cancel_keeps_incomplete_phase_and_sentinel(self):
        self.enable()
        sentinel = subprocess.Popen(['sleep', '30'])
        self.addCleanup(sentinel.wait)
        self.addCleanup(lambda: sentinel.kill() if sentinel.poll() is None else None)
        for index, mode in enumerate(('timeout', 'cancel')):
            with self.subTest(mode=mode):
                self.ready.unlink(missing_ok=True)
                task = f'axes-1800000001-{130 + index}'
                request = f'mix-request-1800000001-{130 + index}'
                pidfile = self.module / '.luoshu-state/tasks/axes_worker.pid'
                env = {**self.env, 'LUOSHU_MIX_REQUEST_ID': request,
                       'LUOSHU_MIX_PHASE_OUTER_TASK': task, 'FIXED_HOLD': '1'}
                proc = subprocess.Popen([sys.executable, str(self.module / 'common/task_scope.py'),
                                         'run', '--pid-file', str(pidfile), '--task', task,
                                         '--timeout', '2' if mode == 'timeout' else '15', '--',
                                         'sh', str(self.driver), *map(str, self.sources)],
                                        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                deadline = time.monotonic() + 5
                while not self.ready.exists() and proc.poll() is None and time.monotonic() < deadline:
                    time.sleep(.02)
                self.assertTrue(self.ready.exists())
                owner = json.loads(Path(str(pidfile) + '.owner.json').read_text())
                if mode == 'cancel':
                    cancel = subprocess.run([sys.executable, str(self.module / 'common/task_scope.py'),
                                             'cancel', str(pidfile), task], env=env, capture_output=True, text=True, timeout=8)
                    self.assertEqual(cancel.returncode, 0, cancel.stdout + cancel.stderr)
                stdout, stderr = proc.communicate(timeout=8)
                self.assertEqual(proc.returncode, 124 if mode == 'timeout' else 143, stdout + stderr)
                proof = json.loads(Path(str(pidfile) + '.cleanup.json').read_text())
                self.assertTrue(proof['cleaned'])
                self.assertFalse(Path(owner['temporary']).exists())
                records = [v for v in events(self.module) if v['request'] == request]
                runner = [v for v in records if v['phase'] == 'cold_composite_runner']
                self.assertEqual([v['event'] for v in runner], ['begin'], runner)
                timing = diagnostic.collect_mix_timings(self.module)
                latest = timing['requests'][-1]
                self.assertEqual(latest['backendTotal']['reason'], 'timeout' if mode == 'timeout' else 'cancelled', latest)
                self.assertTrue(latest['backendTotal']['cleaned'])
                self.assertTrue(any(v['status'] == 'incomplete' for v in latest['phases']))
                self.assertIsNone(sentinel.poll())
                self.assertEqual(self.sentinel_file.read_text(), 'preserved')
                self.assertFalse(list(self.cache.glob('*.otf')))

    def test_diagnostic_append_failure_does_not_change_actual_font_result(self):
        self.enable()
        _, font = self.good()
        original = digest(font)
        logfile = self.module / 'logs/fontswitch.log'
        logfile.unlink(); logfile.mkdir()
        warm, again = self.good()
        self.assertEqual(warm.data['cacheHit'], 'true')
        self.assertEqual(digest(again), original)
        self.assertEqual((self.count(self.calls), self.count(self.validations)), (1, 1))

    def test_auto_actual_composite_cold_warm_and_unknown_context(self):
        auto = auto_fixture.LegacyMixPrepareReuse(methodName='runTest')
        auto.setUp(); self.addCleanup(auto.doCleanups)
        auto.env.update(LUOSHU_MIX_REQUEST_ID='mix-request-1800000002-140',
                        LUOSHU_MIX_PHASE_OUTER_TASK='auto-mix-1800000002-140',
                        LUOSHU_TASK_SCOPE_TASK='auto-mix-1800000002-140')
        auto.prepare_composite_inputs()
        cold = auto.composite()
        self.assertEqual(cold.returncode, 0, cold.stderr)
        original = (auto.taskroot / 'result.ttf').read_bytes()
        before = events(auto.module)
        self.assertTrue(self.completed('cold_composite_runner', before))
        warm = auto.composite('warm')
        self.assertEqual(warm.returncode, 0, warm.stderr)
        self.assertEqual((auto.taskroot / 'warm.ttf').read_bytes(), original)
        self.assertEqual(auto.composite_count(), 1)
        recent = events(auto.module)[len(before):]
        self.assertEqual([v['phase'] for v in recent if v['event'] == 'end'], ['cache_lookup', 'reuse_output'])
        self.assertEqual(len(next(auto.composite_cache().glob('*.receipt')).read_text().splitlines()), 4)
        size = len(events(auto.module))
        unknown = auto.composite('unknown', extra_env={'LUOSHU_MIX_REQUEST_ID': 'private-family/path'})
        self.assertEqual(unknown.returncode, 0, unknown.stderr)
        self.assertEqual(len(events(auto.module)), size)

    def test_logger_long_uptime_uses_relative_arithmetic_and_preserves_rc(self):
        self.enable()
        helper = ROOT / 'common/legacy_v14_4/mix_phase_timing.sh'
        code = f'''. "{helper}"
LOG_FILE="$MODDIR/logs/fontswitch.log"
mkdir -p "$MODDIR/logs"
_clock_calls=0
_luompt_clock() {{
    _clock_calls=$((_clock_calls + 1))
    _luompt_now_s=3000000
    _luompt_now_ms=120
    [ "$_clock_calls" != 2 ] || _luompt_now_ms=150
    _luompt_raw="$_luompt_now_s.$_luompt_now_ms"
}}
luoshu_mix_phase_run prepare prepare cjk prepare sh -c 'exit 7'
test "$?" = 7
'''
        result = subprocess.run(['sh', '-c', code], env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.completed('prepare')[-1]['elapsedMs'], '30')
        self.assertEqual(self.completed('prepare')[-1]['result'], 'failed')

    def test_logger_missing_clock_keeps_original_nonzero_rc(self):
        self.enable()
        helper = ROOT / 'common/legacy_v14_4/mix_phase_timing.sh'
        code = f'''. "{helper}"
LOG_FILE="$MODDIR/logs/fontswitch.log"
_luompt_clock() {{ return 1; }}
luoshu_mix_phase_run prepare prepare cjk prepare sh -c 'exit 7'
exit "$?"
'''
        result = subprocess.run(['sh', '-c', code], env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 7, result.stderr)
        self.assertEqual(events(self.module), [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
