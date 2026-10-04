#!/usr/bin/env python3
"""Real shell App-router snapshots, including an atomic pathname replacement."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / 'common/legacy_v14_4/mix_router.sh'
OLD_TORN = False

class MixSnapshotContractTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.module = Path(self.temp.name) / 'module'
        self.config = self.module / 'config'
        self.config.mkdir(parents=True)
        self.task = self.config / 'axes_task.conf'

    def call(self, command='status', wanted='', *, swap=None):
        source = ROUTER.read_text()
        if swap is not None:
            incoming = self.config / 'incoming.conf'
            incoming.write_text(swap)
            # Replace the pathname exactly after the first consumed field.
            # Worker liveness is separately tested by legacy_mix_status_lifecycle_test.py.
            hooks = r'''
mix_reconcile_fast() { :; }
snapshot_test_swap() {
    [ ! -f "$SNAPSHOT_SWAP_NEXT" ] || mv -f "$SNAPSHOT_SWAP_NEXT" "$REALMOD/config/axes_task.conf"
}
read() {
    command read "$@"
    _snapshot_read_rc=$?
    snapshot_test_swap
    return "$_snapshot_read_rc"
}
read_value() {
    _snapshot_value=$(sed -n "s/^$2=//p" "$1" 2>/dev/null | head -n1 | tr -d '\r\n')
    [ "$2" != task ] || snapshot_test_swap
    printf '%s' "$_snapshot_value"
}
'''
            marker = '_cmd="${1:-config}"'
            self.assertIn(marker, source)
            source = source.replace(marker, hooks + '\n' + marker)
        script = Path(self.temp.name) / 'router.sh'
        script.write_text(source)
        env = {**os.environ, 'MODDIR': str(self.module), 'LUOSHU_MIX_DIAGNOSTICS': '0'}
        if swap is not None:
            env['SNAPSHOT_SWAP_NEXT'] = str(incoming)
        result = subprocess.run(['sh', str(script), command, wanted], env=env,
                                text=True, capture_output=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.module / '.legacy-v14-runtime').exists())
        self.assertFalse((self.module / '.luoshu-mix-stage').exists())
        self.assertEqual(result.stderr, '')
        return json.loads(result.stdout)

    def write(self, **values):
        self.task.write_text('\n'.join(f'{k}={v}' for k, v in values.items()) + '\n')

    def test_unicode_literals_and_axes_preserve_wire_fields(self):
        self.write(task='axes-one', state='running', message='中文 "消息" \\ 字面 $()',
                   percent=34, cjk='甲=乙', latin='Latin', digit='Digits',
                   cjkAxes='wght=440,wdth=101')
        data = self.call(wanted='axes-one')['data']
        self.assertEqual((data['task'], data['state'], data['message'], data['cjk']),
                         ('axes-one', 'running', '中文 "消息" \\ 字面 $()', '甲=乙'))
        self.assertEqual(data['cjkAxes'], 'wght=440,wdth=101')
        self.assertEqual((data['latinAxes'], data['digitAxes']), ('wght=400', 'wght=400'))
        self.assertEqual(data['progress'], {'message': data['message'], 'percent': 34})
        self.assertEqual((data['timeout'], data['cjkWeight']), (720, 400))

    def test_crlf_duplicate_keys_keep_first_value(self):
        self.task.write_bytes(b'task=first\r\nstate=running\r\npercent=9\r\n'
                              b'task=second\r\ncjk=first-font\r\ncjk=other\r\n')
        data = self.call(wanted='first')['data']
        self.assertEqual((data['task'], data['cjk'], data['progress']['percent']),
                         ('first', 'first-font', 9))

    def test_mismatched_task_is_rejected(self):
        self.write(task='current', state='running')
        self.assertEqual(self.call(wanted='other')['status'], 'error')

    def test_absent_config_uses_existing_defaults(self):
        data = self.call('config')['data']
        self.assertFalse(data['enabled'])
        self.assertEqual([data[k] for k in ('cjkWeight', 'latinWeight', 'digitWeight')], [400]*3)
        self.assertEqual([data[k] for k in ('cjkAxes', 'latinAxes', 'digitAxes')], ['wght=400']*3)

    def test_config_weights_axes_and_first_occurrences(self):
        (self.config / 'axes_mix.conf').write_text(
            'cjk=CJK\nlatin=Latin\ndigit=Digits\ncjkWeight=550\nlatinWeight=oops\n'
            'digitWeight=700\ncjkAxes=wght=550,wdth=90\ncjkWeight=999\n')
        data = self.call('config')['data']
        self.assertEqual((data['cjkWeight'], data['latinWeight'], data['digitWeight']), (550,400,700))
        self.assertEqual((data['cjkAxes'], data['latinAxes'], data['digitAxes']),
                         ('wght=550,wdth=90','wght=400','wght=700'))

    def test_success_requires_prepared_next_payload(self):
        self.write(task='done', state='success', message='compiled', percent=100)
        data = self.call()['data']
        self.assertEqual((data['state'], data['progress']['percent']), ('running',99))
        (self.module / '.luoshu-payload-next').mkdir()
        (self.config / 'font-payload-next.conf').write_text('font=mix\n')
        data = self.call()['data']
        self.assertEqual((data['state'], data['message'], data['progress']['percent']),
                         ('success','compiled',100))

    def test_failed_finalization_is_not_success(self):
        self.write(task='done', state='success', message='compiled', percent=100)
        (self.config / 'mix-finalize-state.conf').write_text('state=failed\nmessage=commit failed\n')
        data = self.call()['data']
        self.assertEqual((data['state'],data['message']), ('failed','commit failed'))

    def test_atomic_replacement_keeps_one_generation(self):
        self.write(task='old', state='running', message='old message', percent=23, cjk='old-font')
        data = self.call(wanted='old', swap='task=new\nstate=queued\nmessage=new message\npercent=54\ncjk=new-font\n')['data']
        actual = (data['task'],data['state'],data['message'],data['cjk'],data['progress']['percent'])
        expected = ('old','queued','new message','new-font',54) if OLD_TORN else ('old','running','old message','old-font',23)
        self.assertEqual(actual, expected)
        self.assertIn('task=new\n', self.task.read_text())

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--old-source', type=Path)
    args, remaining = parser.parse_known_args()
    if args.old_source:
        ROUTER = args.old_source
        OLD_TORN = True
        remaining = ['MixSnapshotContractTest.test_atomic_replacement_keeps_one_generation']
    print(json.dumps({'scope':'HOST_REAL_SHELL_APP_ROUTER_NOT_ANDROID_OR_MOUNTS',
                      'source':str(ROUTER), 'old_torn_control':OLD_TORN}), flush=True)
    unittest.main(argv=[__file__]+remaining)
