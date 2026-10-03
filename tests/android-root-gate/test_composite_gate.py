"""Synthetic evidence tests, never represented as an Android execution report."""
import errno
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from composite_gate import composite_blockers, fields, last_json, run
from commit_lock_device import fd_observation


def valid_composite():
    sources = dict(cjk='synthetic-a', latin='synthetic-b', digit='synthetic-b')
    generation = dict(sources, requestId='mix-request-123', compositeHash='e' * 64)
    boot = dict(before='11111111-1111-1111-1111-111111111111', after='22222222-2222-2222-2222-222222222222')
    return dict(result='PASS', entry='common/font_mix_controller.sh start', sources=sources,
        commit_lock_probe=dict(result='PASS', environment='ACTUAL_ANDROID_QEMU_ROOT_ENFORCING',
            unexported_fd_control=dict(exit=0, fstat_errno=9, flock_errno=9),
            caller_retains_lock=dict(result='PASS', errno=11),
            contention=dict(exit=1, stderr='[task-scope] lock-fd timeout fd=9 errno=11 (EAGAIN)'),
            waiter_blocked_while_owned=True, owner_release=dict(exit=0),
            waiter_after_release=dict(exit=0, stdout='ACQUIRED\n'), persistent_inode_preserved=True),
        task=dict(status='ok', data=dict(sources, task='axes-1', state='success')),
        axes_task=dict(sources, task='axes-1', childTask='mix-1', state='success'),
        engine_task=dict(task='mix-1', state='success'),
        background_finalize=dict(requestId='mix-request-123', state='success'),
        generation_manifest=generation, next_state=dict(generation, state='prepared', font='mix'),
        next_payload_hashes={'/next/font.otf': 'e' * 64},
        background_monitor_committed=True, live_unchanged_before_reboot=True,
        concurrent_finalize=[dict(exit=0, response=dict(status='ok')) for _ in range(3)],
        concurrent_finalize_unchanged=True, stage_cleared=True, worker_sidecars_cleared=True, worker_sidecars=[], stage_cleared_after_replay=True,
        reboot=boot, activated_state=dict(generation, font='mix'),
        mounted=dict(font='mix', changed=['/system/fonts/a.ttf'],
            mount_proofs={'/system/fonts/a.ttf': {'canonical':'/system/fonts/a.ttf','mount_records':[['actual-proof']]}}),
        restore=dict(data=dict(state='success')), restore_reboot=boot, restore_hashes_equal_stock=True)


class CompositeVerdictTests(unittest.TestCase):
    def test_complete_evidence(self):
        self.assertEqual(composite_blockers(valid_composite()), [])

    def test_missing_required_evidence_blocks(self):
        for key in valid_composite():
            report = valid_composite(); del report[key]
            self.assertTrue(composite_blockers(report), key)

    def test_generated_engine_success_does_not_hide_failed_commit(self):
        report = valid_composite()
        report['background_finalize']['state'] = 'failed'
        report['task']['data']['state'] = 'running'
        self.assertTrue(composite_blockers(report))

    def test_stale_task_request_digest_or_sources_block(self):
        for where, key in (('axes_task','task'), ('axes_task','childTask'),
                           ('background_finalize','requestId'), ('generation_manifest','requestId'),
                           ('generation_manifest','compositeHash'), ('next_state','cjk'),
                           ('activated_state','requestId')):
            report = valid_composite(); report[where][key] = 'stale'
            self.assertTrue(composite_blockers(report), (where, key))

    def test_raw_fd_failure_cannot_be_counted_as_contention(self):
        report = valid_composite()
        report['commit_lock_probe']['contention']['stderr'] = 'errno=9 (EBADF)'
        self.assertTrue(composite_blockers(report))

    def test_waiter_must_retain_lock_until_release(self):
        for key in ('waiter_blocked_while_owned', 'persistent_inode_preserved'):
            report = valid_composite(); report['commit_lock_probe'][key] = False
            self.assertTrue(composite_blockers(report), key)

    def test_live_mutation_missing_mount_or_failed_replay_blocks(self):
        report = valid_composite(); report['live_unchanged_before_reboot'] = False
        self.assertTrue(composite_blockers(report))
        report = valid_composite(); report['mounted']['mount_proofs'] = {}
        self.assertTrue(composite_blockers(report))
        report = valid_composite(); report['concurrent_finalize'][0]['exit'] = 1
        self.assertTrue(composite_blockers(report))

    def test_malformed_evidence_fails_closed(self):
        for value in (None, [], dict(result='PASS', sources=None), dict(commit_lock_probe=[])):
            self.assertTrue(composite_blockers(value))

    def test_json_and_state_parsers_do_not_confuse_progress(self):
        self.assertEqual(last_json('progress\n{"status":"ok"}\n'), {'status':'ok'})
        self.assertEqual(fields('cjkAxes=wght=400\nstate=success'), {'cjkAxes':'wght=400','state':'success'})
        with self.assertRaises(RuntimeError):
            last_json('no JSON')

    def test_failed_monitor_is_never_rescued_by_manual_finalize(self):
        calls = []
        evidence = valid_composite()
        def root(command, **kwargs):
            calls.append(command)
            if command.startswith('cat /data/local/tmp/luoshu-commit-lock-device-'):
                import json
                return json.dumps(evidence['commit_lock_probe'])
            if 'font_mix_controller.sh start' in command:
                return '{"status":"ok","data":{"task":"axes-1"}}'
            if command.startswith('for f in axes_task.conf'):
                return ('GATE_FILE:axes_task.conf\ntask=axes-1\nstate=success\n'
                        'GATE_FILE:mix_task.conf\ntask=mix-1\nstate=success\n'
                        'GATE_FILE:mix-finalize-state.conf\nstate=failed\n')
            return ''
        report = {}
        with tempfile.TemporaryDirectory() as output:
            with self.assertRaisesRegex(RuntimeError, 'background finalizer failed'):
                run(report, '/module', root, lambda *a: None, None,
                    lambda: {'font':'stock'}, None, None, {}, ['synthetic-a','synthetic-b'], output)
        self.assertFalse(any('mix_router.sh finalize' in call for call in calls))
        self.assertEqual(report['result'], 'FAIL')

    def test_stale_pass_cannot_mask_probe_start_failure_or_crash(self):
        import json
        stale_path = '/data/local/tmp/luoshu-commit-lock-device.json'
        for failure, current_output in (
                ('executable could not start', ''),
                ('probe crashed', json.dumps(valid_composite()['commit_lock_probe']))):
            with self.subTest(failure=failure):
                calls = []
                report = {}
                def root(command, **kwargs):
                    calls.append(command)
                    if command.startswith('PYTHONHOME='):
                        self.assertIs(kwargs.get('required'), True)
                        raise RuntimeError(failure)
                    if command == 'cat ' + stale_path:
                        return json.dumps(valid_composite()['commit_lock_probe'])
                    if command.startswith('cat /data/local/tmp/luoshu-commit-lock-device-'):
                        return current_output
                    self.fail('Generation must not begin after a failed lock probe: ' + command)
                with tempfile.TemporaryDirectory() as output:
                    with self.assertRaisesRegex(RuntimeError, 'did not exit successfully'):
                        run(report, '/module', root, lambda *a: None, None,
                            lambda: {}, None, None, {}, ['a','b'], output)
                self.assertNotIn('cat ' + stale_path, calls)
                self.assertNotEqual(report['commit_lock_probe_output'], stale_path)
                self.assertEqual(report['commit_lock_probe']['result'], 'FAIL')
                self.assertEqual(report['commit_lock_probe']['execution_error'], failure)
                self.assertEqual(report['commit_lock_probe']['output_after_failure'], current_output)
                self.assertTrue(composite_blockers(report))

    def test_monitor_marker_and_stage_cleanup_precede_any_manual_replay(self):
        import json
        for leftover_stage in (False, True):
            with self.subTest(leftover_stage=leftover_stage):
                expected = valid_composite()
                report = {}
                calls = []
                marker_reads = 0
                def conf(value):
                    return ''.join(f'{key}={item}\n' for key, item in value.items())
                def root(command, **kwargs):
                    nonlocal marker_reads
                    calls.append(command)
                    if command.startswith('PYTHONHOME='):
                        return ''
                    if command.startswith('cat /data/local/tmp/luoshu-commit-lock-device-'):
                        return json.dumps(expected['commit_lock_probe'])
                    if 'font_mix_controller.sh start' in command:
                        return '{"status":"ok","data":{"task":"axes-1"}}'
                    if command.startswith('for f in axes_task.conf'):
                        return ''.join('GATE_FILE:' + name + '\n' + conf(expected[key]) for name, key in (
                            ('axes_task.conf','axes_task'), ('mix_task.conf','engine_task'),
                            ('mix-finalize-state.conf','background_finalize')))
                    if command.startswith('tail -n 240 '):
                        marker_reads += 1
                        return ('monitor finishing' if marker_reads == 1 else
                                'legacy-v14 composite task committed for next boot: mix-1')
                    if 'font_mix_controller.sh status' in command:
                        return json.dumps(expected['task'])
                    if command == 'cat /module/config/font-payload-next.conf':
                        return conf(expected['next_state'])
                    if command == 'cat /module/.luoshu-payload-next/.luoshu-mix-generation.conf':
                        return conf(expected['generation_manifest'])
                    if command.startswith('find /module/.luoshu-payload-next '):
                        return 'e' * 64 + '  /next/font.otf'
                    if command.startswith('test ! -e /module/.luoshu-mix-stage'):
                        if leftover_stage:
                            raise RuntimeError('background monitor left stage or state')
                        return ''
                    if command == 'cat /module/config/font-payload-activated.conf':
                        return conf(expected['activated_state'])
                    if command.startswith('cat /data/local/tmp/luoshu-finalize-gate-'):
                        return '0' if '/rc-' in command else '{"status":"ok"}'
                    if 'mix_router.sh finalize' in command:
                        self.assertGreaterEqual(marker_reads, 2)
                        self.assertIs(report.get('background_monitor_committed'), True)
                        self.assertIs(report.get('stage_cleared'), True)
                        self.assertIs(report.get('worker_sidecars_cleared'), True)
                        return ''
                    if command.startswith(('test ! -e /module/.luoshu-payload-next',
                                           'for p in ', 'mkdir /data/local/tmp/',
                                           'rm -f /data/local/tmp/')):
                        return ''
                    self.fail('Unexpected fake-root command: ' + command)
                with tempfile.TemporaryDirectory() as output, patch('composite_gate.time.sleep'):
                    def invoke():
                        run(report, '/module', root, lambda *a: None,
                            lambda: expected['reboot'], lambda: {'font':'stock'},
                            lambda *a: ({}, expected['mounted']), lambda *a: expected['restore'],
                            {'font':'stock'}, ['synthetic-a','synthetic-b'], output)
                    if leftover_stage:
                        with self.assertRaisesRegex(RuntimeError, 'left stage or state'):
                            invoke()
                        self.assertFalse(any('mix_router.sh finalize' in call for call in calls))
                    else:
                        invoke()
                        self.assertEqual(report['result'], 'PASS')
                        self.assertGreaterEqual(marker_reads, 2)
                        self.assertTrue(any('mix_router.sh finalize' in call for call in calls))

    def test_fd_probe_preserves_errno_without_android_claim(self):
        # Use an intentionally invalid fd, leaving this process's descriptors alone.
        observation = fd_observation(1000000)
        self.assertEqual(observation['fstat_errno'], errno.EBADF)
        self.assertEqual(observation['flock_errno'], errno.EBADF)
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'probe.json'
            result = subprocess.run([sys.executable, str(Path(__file__).with_name('commit_lock_device.py')),
                '--module', temp, '--output', str(output)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn('Only the authorized root Enforcing Android emulator', output.read_text())
