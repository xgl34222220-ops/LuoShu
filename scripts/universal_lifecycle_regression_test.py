#!/usr/bin/env python3
"""Lifecycle failures: real shell control flow, temp modules, no real mounts."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(os.environ.get('LUOSHU_AUDIT_ROOT', Path(__file__).resolve().parents[1]))
sys.path[:0] = [str(ROOT / 'common'), str(ROOT / 'scripts')]
import universal_font_deployment as deployment


def run(script: Path, *args: str, env=None):
    return subprocess.run(['sh', str(script), *args], env=os.environ | (env or {}),
                          text=True, capture_output=True, timeout=25)


def put(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


class LifecycleTests(unittest.TestCase):
    def test_sealed_execution_set(self):
        import universal_font_deployment_test as fixture
        original = deployment.build_deployment
        class Complete(Exception): pass
        def inspect(*args, **kwargs):
            manifest = original(*args, **kwargs)
            root = Path(args[3])
            conf = root / '.luoshu-runtime/deployment/dynamic-mounts.conf'
            content = conf.read_text()
            conf.write_text(content.replace('/data/fonts/files/Runtime-Regular.ttf', '/data/fonts/files/UNPLANNED.ttf'))
            with self.assertRaises(deployment.DeploymentError):
                deployment.validate_payload_integrity(manifest, root)
            conf.write_text(content)
            extra = root / 'system/fonts/UNPLANNED.ttf'; extra.write_bytes(b'undeclared')
            with self.assertRaises(deployment.DeploymentError):
                deployment.validate_payload_integrity(manifest, root)
            extra.unlink()
            extra.symlink_to(root / '.luoshu-runtime/deployment/font-plan.json')
            with self.assertRaises(deployment.DeploymentError):
                deployment.validate_payload_integrity(manifest, root)
            extra.unlink()
            deployment.validate_payload_integrity(manifest, root)
            raise Complete
        deployment.build_deployment = inspect
        try:
            with self.assertRaises(Complete): fixture.main()
        finally:
            deployment.build_deployment = original

    def test_activation_write_failure_restores_legacy_mode(self):
        # Existing fixture setup, then fail exactly the activation metadata rename.
        source = (ROOT / 'scripts/universal_cutover_next_boot_test.sh').read_text()
        source = source[:source.index('universal_font_next_boot_activate\n')]
        source = source.replace('ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"', f'ROOT="{ROOT}"')
        source += '''mv() { case "$*" in *universal-font-activated.conf*) return 1;; esac; command mv "$@"; }
universal_font_next_boot_activate
[ "$?" -eq 1 ] || exit 5
test -f "$MOD/.luoshu-payload/old/file" || exit 6
test -f "$MOD/config/font_runtime_legacy_v14_4.conf" || exit 7
'''
        with tempfile.TemporaryDirectory() as raw:
            script=Path(raw)/'activate.sh'; script.write_text(source)
            result=run(script)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_rollback_concurrent_new_commit_wins(self):
        with tempfile.TemporaryDirectory() as raw:
            t=Path(raw); mod=t/'module'; cfg=mod/'config'; retired=mod/'.luoshu-retired/universal-test'
            put(retired/'old', 'oldpayload')
            py=mod/'common/python/bin/luoshu-python'
            put(py, '#!/bin/sh\nunset PYTHONHOME PYTHONPATH\nexec '+sys.executable+' "$@"\n'); py.chmod(0o755)
            put(cfg/'universal-font-runtime-verification.conf','grade=FAIL\nbootId=boot-test\n')
            put(cfg/'universal-font-activated.conf',f'bootId=boot-test\npreviousFont=OldFont\nfont=FailedFont\npreviousMode=legacy\nretired={retired}\n')
            if (ROOT/'common/payload_commit_lock.sh').exists():
                put(mod/'common/payload_commit_lock.sh',(ROOT/'common/payload_commit_lock.sh').read_text())
            # The foreground commit starts during rollback's copy, through the
            # same public commit lease used by all production writers.
            writer=t/'writer.sh'
            writer.write_text('''#!/bin/sh
commit() {
 rm -rf "$MOD/.luoshu-payload-next"
 mkdir -p "$MOD/.luoshu-payload-next"
 printf newchoice > "$MOD/.luoshu-payload-next/newchoice"
 rm -f "$MOD/config/font-payload-next.conf"
 printf 'state=prepared\nfont=NewUserChoice\n' > "$MOD/config/universal-font-next.conf"
 printf 'NewUserChoice\n' > "$MOD/config/active_font.conf"
 touch "$DONE"
}
if [ -f "$MOD/common/payload_commit_lock.sh" ]; then
 . "$MOD/common/payload_commit_lock.sh"
 luoshu_payload_commit_run "$MOD" commit
else commit; fi
''')
            cp=t/'bin/cp'; put(cp,'''#!/bin/sh
/bin/cp "$@" || exit $?
sh "$WRITER" > "$WRITER_LOG" 2>&1 &
sleep 1
''');cp.chmod(0o755)
            env={'MOD':str(mod),'MODDIR':str(mod),'PATH':str(t/'bin')+':'+os.environ['PATH'],
                 'WRITER':str(writer),'DONE':str(t/'done'),'WRITER_LOG':str(t/'writer.log')}
            result=run(ROOT/'common/universal_font_cutover.sh','rollback-from-fail','boot-test',env=env)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            # Await bounded foreground completion; locking release is deterministic.
            import time
            until=time.monotonic()+8
            while not (t/'done').exists() and time.monotonic()<until: time.sleep(.05)
            self.assertTrue((t/'done').exists(), (t/'writer.log').read_text())
            self.assertTrue((mod/'.luoshu-payload-next/newchoice').exists())
            self.assertIn('NewUserChoice',(cfg/'universal-font-next.conf').read_text())
            self.assertFalse((cfg/'font-payload-next.conf').exists())

    def test_failed_verifier_cannot_reuse_pass_or_release_recovery(self):
        with tempfile.TemporaryDirectory() as raw:
            t=Path(raw); mod=t/'module'; cfg=mod/'config'; root=mod/'.luoshu-payload/.luoshu-runtime/deployment'
            for name in ['deployment.json','font-plan.json','artifact-manifest.json']: put(root/name,'{}')
            put(cfg/'universal-font-runtime.conf','state=active\nfont=Demo\ndeploymentId=id\npayloadDigest=digest\n')
            put(cfg/'universal-font-runtime-verification.conf','grade=PASS\nbootId=previous-boot\n')
            retired=mod/'.luoshu-retired/universal-old';put(retired/'font','recovery')
            put(cfg/'universal-font-activated.conf',f'retired={retired}\n')
            result=run(ROOT/'common/universal_font_runtime_verify.sh','run',env={
                'MODDIR':str(mod),'LUOSHU_PYTHON':'/bin/false','LUOSHU_VERIFY_BOOT_COMPLETED':'1',
                'LUOSHU_VERIFY_SETTLE_SECONDS':'0','LUOSHU_VERIFY_STATE_ROOT':str(t/'state')})
            self.assertNotEqual(result.returncode,0)
            self.assertTrue(retired.exists())
            self.assertIn('grade=FAIL',(cfg/'universal-font-runtime-verification.conf').read_text())
            self.assertNotIn('bootId=previous-boot',(cfg/'universal-font-runtime-verification.conf').read_text())

    def test_default_pending_and_stale_boot_status(self):
        with tempfile.TemporaryDirectory() as raw:
            mod=Path(raw); cfg=mod/'config'
            put(mod/'module.prop','id=LuoShu\nversion=test\nversionCode=1\n')
            put(cfg/'active_font.conf','default\n');put(cfg/'text_reboot_required.conf','font=default\n')
            result=run(ROOT/'common/app_bridge.sh','status',env={'MODDIR':str(mod)})
            data=json.loads(result.stdout)['data']
            self.assertEqual(data['fontEffectState'],'pending-reboot')
            self.assertNotEqual(data['effectiveActive'],'default')
            (cfg/'text_reboot_required.conf').unlink(); put(cfg/'active_font.conf','Demo\n')
            put(cfg/'universal-font-runtime.conf','font=Demo\ndeploymentId=id\npayloadDigest=digest\n')
            put(cfg/'universal-font-runtime-verification.conf','grade=PASS\nactiveFont=Demo\nbootId=previous-boot\n')
            put(cfg/'universal-font-mount.conf','state=mounted\n')
            data=json.loads(run(ROOT/'common/app_bridge.sh','status',env={'MODDIR':str(mod)}).stdout)['data']
            self.assertNotEqual(data['fontEffectState'],'verified')

    def test_dynamic_rw_or_foreign_mount_is_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            t=Path(raw);mod=t/'module'; cfg=mod/'config';p=mod/'.luoshu-payload';dest=t/'visible/data/fonts/files/font.ttf'
            put(mod/'common/universal_font_deployment.py','raise SystemExit(0)')
            put(p/'.luoshu-runtime/deployment/deployment.json','{}')
            put(p/'.luoshu-dynamic/font.ttf','font');put(dest,'font')
            h=hashlib.sha256(b'font').hexdigest()
            put(p/'.luoshu-runtime/deployment/dynamic-mounts.conf',f'.luoshu-dynamic/font.ttf|/data/fonts/files/font.ttf|{h}\n')
            put(cfg/'universal-font-runtime.conf','state=active\npipeline=universal-font-deployment-v1\nfont=Demo\n')
            for mode in ['rw','ro']:
                put(t/'mountinfo',f'1 0 0:1 / {dest} {mode},relatime - ext4 x {mode}\n')
                result=run(ROOT/'common/universal_mount_runtime.sh','hook','post-fs-data',env={
                    'MODDIR':str(mod),'LUOSHU_PYTHON':'python3','LUOSHU_UNIVERSAL_TEST_MANAGER':'Magisk',
                    'LUOSHU_UNIVERSAL_TEST_VISIBLE_ROOT':str(t/'visible'),
                    'LUOSHU_UNIVERSAL_MOUNT_STATE_ROOT':str(t/'state'),
                    'LUOSHU_UNIVERSAL_MOUNTINFO':str(t/'mountinfo')})
                self.assertEqual(result.returncode,1,mode+result.stdout+result.stderr)
                self.assertIn('state=failed',(cfg/'universal-font-mount.conf').read_text())
            # The module may idempotently reuse only its own current-boot RO mount.
            put(t/'state/dynamic.mounts',str(dest)+'\n')
            put(t/'state/boot-id',Path('/proc/sys/kernel/random/boot_id').read_text())
            result=run(ROOT/'common/universal_mount_runtime.sh','hook','post-fs-data',env={
                'MODDIR':str(mod),'LUOSHU_PYTHON':'python3','LUOSHU_UNIVERSAL_TEST_MANAGER':'Magisk',
                'LUOSHU_UNIVERSAL_TEST_VISIBLE_ROOT':str(t/'visible'),
                'LUOSHU_UNIVERSAL_MOUNT_STATE_ROOT':str(t/'state'),
                'LUOSHU_UNIVERSAL_MOUNTINFO':str(t/'mountinfo')})
            self.assertEqual(result.returncode,0,result.stderr)

    def test_commit_lease_crash_nested_and_background(self):
        import time
        shell=os.environ.get('LUOSHU_LOCK_TEST_SHELL') or shutil.which('mksh') or 'sh'
        def lease_run(script, env):
            return subprocess.run([shell,str(script)], env=os.environ|env,
                                  text=True,capture_output=True,timeout=25)
        with tempfile.TemporaryDirectory() as raw:
            t=Path(raw); mod=t/'module'
            # Host stand-in for the bundled Android Python; real packaged fcntl
            # is separately required by release runtime validation.
            py=mod/'common/python/bin/luoshu-python'
            put(py, '#!/bin/sh\nunset PYTHONHOME PYTHONPATH\nexec '+sys.executable+' "$@"\n'); py.chmod(0o755)
            helper=ROOT/'common/payload_commit_lock.sh'
            native=os.environ.get('LUOSHU_LOCK_TEST_FLOCK') or shutil.which('toybox')
            native_path=os.environ['PATH']
            if native:
                (t/'native-bin').mkdir()
                (t/'native-bin/flock').symlink_to(Path(native).resolve())
                native_path=str(t/'native-bin')+':'+native_path
            for backend in ['auto','python']:
                script=t/'lease.sh'
                script.write_text(f'''#!/bin/sh
. "{helper}"
nested() {{
 luoshu_payload_commit_run "$MOD" true
 [ "$?" -ne 0 ] || exit 7
 sleep 6 >/dev/null 2>&1 &
 printf '%s\\n' "$!" > "$MOD/background.pid"
}}
luoshu_payload_commit_run "$MOD" nested || exit 8
LUOSHU_PAYLOAD_LOCK_TIMEOUT=1 luoshu_payload_commit_run "$MOD" true || exit 9
kill "$(cat "$MOD/background.pid")" 2>/dev/null || true
''')
                env={'MOD':str(mod),'LUOSHU_PAYLOAD_LOCK_BACKEND':backend,'PATH':native_path}
                result=lease_run(script,env=env)
                self.assertEqual(result.returncode,0,backend+result.stderr)
                # Kill an active lock body. No owner/reaper files need recovery.
                script.write_text(f'''#!/bin/sh
. "{helper}"
hold() {{ touch "$MOD/ready"; sleep 30; }}
luoshu_payload_commit_run "$MOD" hold
''')
                (mod/'ready').unlink(missing_ok=True)
                process=subprocess.Popen([shell,str(script)],env=os.environ|env,start_new_session=True)
                try:
                    deadline=time.monotonic()+3
                    while not (mod/'ready').exists() and time.monotonic()<deadline: time.sleep(.02)
                    self.assertTrue((mod/'ready').exists())
                    probe=t/'probe.sh';probe.write_text(f'. "{helper}"\nluoshu_payload_commit_run "$MOD" true\n')
                    self.assertNotEqual(lease_run(probe,env=env|{'LUOSHU_PAYLOAD_LOCK_TIMEOUT':'0'}).returncode,0)
                    import signal
                    os.killpg(process.pid,signal.SIGKILL);process.wait()
                    self.assertEqual(lease_run(probe,env=env|{'LUOSHU_PAYLOAD_LOCK_TIMEOUT':'1'}).returncode,0)
                finally:
                    if process.poll() is None:
                        os.killpg(process.pid,9); process.wait()

    def test_commit_lock_exec_fd_and_native_ebadf_fallback(self):
        import time
        with tempfile.TemporaryDirectory() as raw:
            t=Path(raw); mod=t/'module'; bin_dir=t/'bin'; bin_dir.mkdir()
            py=mod/'common/python/bin/luoshu-python'
            put(py, '#!/bin/sh\nunset PYTHONHOME PYTHONPATH\nexec '+sys.executable+' "$@"\n')
            py.chmod(0o755)
            # This is a real executable doing real fcntl, with shell-private
            # descriptors closed as on mksh exec. Toybox-compatible error rc=1.
            native=bin_dir/'flock'
            put(native, '#!'+sys.executable+"\n"+"""import fcntl, os, sys
from pathlib import Path
with open(os.environ['LOCK_CALLS'], 'a') as log: log.write('native\\n')
for fd in range(3, 20):
    try: os.close(fd)
    except OSError: pass
fd=int(sys.argv[-1])
if os.environ.get('BREAK_NATIVE') == '1':
    try: os.close(fd)
    except OSError: pass
try: fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
except OSError as error:
    print('flock: flock: '+error.strerror, file=sys.stderr)
    sys.exit(1)
""")
            native.chmod(0o755)
            script=t/'probe.sh'
            put(script, f'. "{ROOT}/common/payload_commit_lock.sh"\n'
                'body() { printf committed > "$MOD/committed"; }\n'
                'luoshu_payload_commit_run "$MOD" body\n')
            env={'MOD':str(mod), 'PATH':str(bin_dir)+':'+os.environ['PATH'],
                 'LOCK_CALLS':str(t/'calls'), 'LUOSHU_PAYLOAD_LOCK_TIMEOUT':'120'}
            shells=['sh']
            if os.environ.get('LUOSHU_LOCK_TEST_SHELL'):
                shells.append(os.environ['LUOSHU_LOCK_TEST_SHELL'])
            elif shutil.which('mksh'):
                shells.append(shutil.which('mksh'))
            for shell in shells:
                for broken in ['0','1']:
                    (mod/'committed').unlink(missing_ok=True)
                    (t/'calls').unlink(missing_ok=True)
                    result=subprocess.run([shell,str(script)], env=os.environ|env|{'BREAK_NATIVE':broken},
                                          text=True,capture_output=True,timeout=4)
                    self.assertEqual(result.returncode,0,result.stderr)
                    self.assertEqual((mod/'committed').read_text(),'committed')
                    self.assertEqual((t/'calls').read_text(),'native\n')
                    self.assertNotIn('Bad file descriptor',result.stderr)
                # Both native and fallback lose their target descriptor: fail
                # once, never retry EBADF for the configured 120 seconds.
                put(py, '#!/bin/sh\nunset PYTHONHOME PYTHONPATH\nexec 0<&-\nexec '+sys.executable+' "$@"\n')
                (mod/'committed').unlink(missing_ok=True)
                (t/'calls').unlink(missing_ok=True)
                started=time.monotonic()
                result=subprocess.run([shell,str(script)],env=os.environ|env|{'BREAK_NATIVE':'1'},
                                      text=True,capture_output=True,timeout=4)
                self.assertNotEqual(result.returncode,0)
                self.assertFalse((mod/'committed').exists())
                self.assertIn('commit lock failed',result.stderr)
                self.assertLess(time.monotonic()-started,3)
                self.assertEqual((t/'calls').read_text(),'native\n')
                put(py, '#!/bin/sh\nunset PYTHONHOME PYTHONPATH\nexec '+sys.executable+' "$@"\n')

    def test_protected_typography_is_reported_partial(self):
        source=(ROOT/'common/universal_font_cutover.sh').read_text()
        body=source.split("<<'PYCOVER'\n",1)[1].split('\nPYCOVER',1)[0]
        with tempfile.TemporaryDirectory() as raw:
            t=Path(raw);route=t/'route.json';artifacts=t/'artifacts.json';output=t/'coverage.conf';plan=t/'plan.json'
            plan.write_text(json.dumps({'targets':{}}))
            route.write_text(json.dumps({'preservedRoutes':[{}]}))
            artifacts.write_text(json.dumps({'artifacts':[{'report':{'transformed':{'layout':{'preservedMathGlyphs':3,'preservedSharedMarks':2,'preservedClockPunctuation':1}}}}]}))
            result=subprocess.run([sys.executable,'-',str(route),str(output),'request-test',str(artifacts),str(plan)],input=body,text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            content=output.read_text()
            self.assertIn('coverage=partial-protected-typography',content)
            self.assertIn('preservedMathGlyphs=3',content)
            self.assertIn('preservedClockPunctuation=1',content)
            self.assertIn('原厂钟表标点',content)
            self.assertIn('preservedSharedMarks=2',content)
            self.assertIn('部分覆盖',content)
            plan.write_text(json.dumps({'targets':{'/system/fonts/Unsealed.ttf':{
                'reasons':['unsealed-physical-candidate']}}}))
            result=subprocess.run([sys.executable,'-',str(route),str(output),'request-test',str(artifacts),str(plan)],input=body,text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
            content=output.read_text()
            self.assertIn('coverage=partial-unverified-originals',content)
            self.assertIn('unsealedPhysicalTargetCount=1',content)
            self.assertIn('无法验证原厂来源的路径未覆盖',content)

    def test_dynamic_generation_changed_is_rejected(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);font='/data/fonts/files/font.ttf';config='/data/fonts/config/config.xml'
            put(root/font.lstrip('/'),'stock');put(root/config.lstrip('/'),'config-v1')
            h=lambda text:hashlib.sha256(text.encode()).hexdigest()
            manifest={'dynamicMounts':[{'targetPath':font,'sha256':h('compiled'),'dynamicIdentity':{
                'fontPath':font,'fontSha256':h('stock'),'configPath':config,'configSha256':h('config-v1')}}]}
            deployment.validate_dynamic_generation(manifest,root)
            put(root/config.lstrip('/'),'config-v2')
            with self.assertRaises(deployment.DeploymentError): deployment.validate_dynamic_generation(manifest,root)

if __name__=='__main__': unittest.main(verbosity=2)
