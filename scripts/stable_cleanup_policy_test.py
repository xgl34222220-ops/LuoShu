#!/usr/bin/env python3
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
ROOT = Path(__file__).resolve().parents[1]
class CleanupPolicy(unittest.TestCase):
    def test_weight_retirement_is_owned_reversible_and_idempotent(self):
        for current, expected in [('50', '20'), ('70', '70')]:
            with self.subTest(current=current), tempfile.TemporaryDirectory() as t:
                d = Path(t); c = d/'module/config'; c.mkdir(parents=True)
                (c/'font_weight.conf').write_text('adjustment=50\n')
                (c/'font_weight_original.conf').write_text('adjustment=20\n')
                (d/'value').write_text(current)
                (d/'settings').write_text('''#!/bin/sh
[ "$1" != --user ] || shift 2
case "$1" in
get) cat "$STATE/value";;
put) echo "$4" > "$STATE/value"; echo write >> "$STATE/writes";;
esac
'''); (d/'settings').chmod(0o755)
                env = {**os.environ, 'PATH':f'{d}:'+os.environ['PATH'], 'STATE':str(d)}
                args = ['sh', str(ROOT/'common/retire_global_weight.sh'),str(d/'module')]
                subprocess.run(args,env=env,check=True)
                subprocess.run(args,env=env,check=True)
                self.assertEqual((d/'value').read_text().strip(),expected)
                self.assertFalse((c/'font_weight.conf').exists())
                self.assertEqual((c/'recovery/retired-global-weight/font_weight.conf').read_text(),'adjustment=50\n')
                if current=='70': self.assertFalse((d/'writes').exists())
                else:self.assertEqual((d/'writes').read_text().splitlines(),['write'])
    def test_missing_original_is_not_guessed(self):
        with tempfile.TemporaryDirectory() as t:
            d=Path(t); (d/'config').mkdir(); (d/'config/font_weight.conf').write_text('adjustment=50\n')
            p=subprocess.run(['sh',str(ROOT/'common/retire_global_weight.sh'),str(d)])
            self.assertNotEqual(p.returncode,0)
            self.assertTrue((d/'config/font_weight.conf').exists())
    def test_legacy_weight_retirement_waits_for_android_boot(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t); module=d/'module'; (module/'common').mkdir(parents=True); (module/'config').mkdir()
            (module/'config/font_runtime_legacy_v14_4.conf').write_text('font=default\n')
            shutil.copyfile(ROOT/'service.sh', module/'service.sh')
            (d/'boot').write_text('0\n')
            (d/'getprop').write_text('#!/bin/sh\ncat "$FIXTURE/boot"\n')
            (d/'sleep').write_text('#!/bin/sh\necho 1 > "$FIXTURE/boot"\n')
            (d/'getprop').chmod(0o755); (d/'sleep').chmod(0o755)
            (module/'common/retire_global_weight.sh').write_text('#!/bin/sh\n[ "$(getprop sys.boot_completed)" = 1 ] || exit 1\ntouch "$FIXTURE/retired"\n')
            env={**os.environ,'PATH':str(d)+':'+os.environ['PATH'],'FIXTURE':str(d)}
            subprocess.run(['sh',str(module/'service.sh')],env=env,capture_output=True,timeout=3,check=True)
            self.assertTrue((d/'retired').exists(), 'legacy route never retired owned global weight after boot')

    def test_defaults_are_bounded_and_no_prewarm(self):
        s=(ROOT/'common/google_font_provider_service.sh').read_text()
        self.assertIn('LUOSHU_GOOGLE_FONT_WATCH_CYCLES:-0',s)
        self.assertIn('LUOSHU_GOOGLE_FONT_RETRIES:-1',s)
        self.assertIn('LUOSHU_GOOGLE_FONT_ALLOW_RESTART:-0',s)
        self.assertNotIn('provider_run "$BRIDGE" refresh', s)
        self.assertNotIn('prewarm-start', (ROOT/'common/app_bridge.sh').read_text())
        for p in ['service.sh','.luoshu-runtime/core/service.sh']:
            self.assertNotIn('action list', (ROOT/p).read_text())
    def test_fingerprint_change_and_access_fail_closed(self):
        with tempfile.TemporaryDirectory() as t:
            d=Path(t); (d/'fonts').mkdir(); (d/'config').mkdir()
            f=d/'fonts/A.ttf';f.write_text('AAAA')
            env={**os.environ,'USER_FONTS_DIR':str(d/'fonts'),'CONFIG_DIR':str(d/'config')}
            cmd=['sh','-c',f'. "{ROOT}/common/font_library_cache.sh"; font_library_fingerprint_value']
            first=subprocess.check_output(cmd,env=env)
            f.chmod(0o600);self.assertNotEqual(first,subprocess.check_output(cmd,env=env))
            shutil.rmtree(d/'fonts')
            self.assertNotEqual(subprocess.run(cmd,env=env,stdout=subprocess.PIPE).returncode,0)
if __name__=='__main__':unittest.main()
