#!/usr/bin/env python3
"""One-shot lifecycle regression: no late-download observer or consumer restarts."""
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time
import unittest
from host_task_scope_fixture import install_task_scope
ROOT = Path(__file__).resolve().parents[1]

class ProviderLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.module = self.root / 'module'
        (self.module/'config').mkdir(parents=True)
        self.active = self.module/'config/active_font.conf'
        self.active.write_text('custom\n')
        install_task_scope(self.module)
        shutil.copyfile(ROOT/'common/font_switch_lock.sh',self.module/'common/font_switch_lock.sh')
        self.bin=self.root/'bin';self.bin.mkdir()
        self.commands('getprop','echo 1\n')
        self.commands('sleep',':\n')
        self.marker=self.root/'applied'
        self.snapshot=self.root/'snapshot';self.snapshot.write_text('boot-cache-and-namespace\n')
        (self.module/'common/google_font_provider_bridge.sh').write_text('''case "$1" in
fingerprint) cat "$TEST_SNAPSHOT";;
apply) printf '%s|%s\n' "$(cat "$TEST_SNAPSHOT")" "$LUOSHU_GOOGLE_FONT_ALLOW_RESTART" >> "$TEST_APPLIED"; exit "${TEST_APPLY_RC:-0}";;
restore) echo restore >> "$TEST_ROOT/restored"; exit "${TEST_RESTORE_RC:-0}";;
esac
''')
        self.env={**os.environ,'MODDIR':str(self.module),'PATH':f'{self.bin}:{os.environ["PATH"]}',
                  'TEST_ROOT':str(self.root),'TEST_SNAPSHOT':str(self.snapshot),'TEST_APPLIED':str(self.marker)}

    def commands(self,name,text):
        p=self.bin/name;p.write_text('#!/bin/sh\n'+text);p.chmod(0o755)

    def service(self, **env):
        result=subprocess.run(['sh',str(ROOT/'common/google_font_provider_service.sh')],
            env={**self.env,**env},text=True,capture_output=True,timeout=10)
        self.assertFalse((self.module/'.google-font-provider.lock').exists())
        self.assertIn('"leftoverPids": []',result.stderr)
        return result

    def applied(self):
        return self.marker.read_text().splitlines() if self.marker.exists() else []

    def test_one_apply_no_consumer_restart(self):
        self.assertEqual(self.service().returncode,0)
        self.assertEqual(self.applied(),['boot-cache-and-namespace|0'])

    def test_old_infinite_watch_configuration_is_ignored(self):
        self.assertEqual(self.service(LUOSHU_GOOGLE_FONT_WATCH_CYCLES='-1',LUOSHU_GOOGLE_FONT_RETRIES='24').returncode,0)
        self.assertEqual(len(self.applied()),1)

    def test_new_download_requires_another_explicit_invocation(self):
        self.service();self.snapshot.write_text('new-download\n')
        self.assertEqual(self.applied(),['boot-cache-and-namespace|0'])
        self.service()
        self.assertEqual(self.applied(),['boot-cache-and-namespace|0','new-download|0'])

    def test_failure_does_not_become_silent_success_or_retry_loop(self):
        self.assertEqual(self.service(TEST_APPLY_RC='1').returncode,1)
        self.assertEqual(len(self.applied()),1)

    def test_interrupted_apply_has_no_automatic_retry(self):
        self.assertEqual(self.service(TEST_APPLY_RC='137').returncode,1)
        self.assertEqual(len(self.applied()),1)

    def test_no_download_is_a_clean_noop(self):
        self.assertEqual(self.service(TEST_APPLY_RC='2').returncode,0)
        self.assertEqual(len(self.applied()),1)

    def theme_fixture(self):
        (self.module/'common/hyperos_theme_font_bridge.sh').write_text('''case "$1" in
readiness) echo 'ready|fixture';;
apply) echo apply >> "$TEST_ROOT/theme-applied"; exit "${TEST_THEME_RC:-0}";;
restore) echo restore >> "$TEST_ROOT/theme-restored"; exit "${TEST_RESTORE_RC:-0}";;
esac
''')

    def test_theme_once_even_when_google_has_no_fonts(self):
        self.theme_fixture();self.assertEqual(self.service(TEST_APPLY_RC='2').returncode,0)
        self.assertEqual((self.root/'theme-applied').read_text().splitlines(),['apply'])

    def test_theme_failure_reported_not_rebuilt_forever(self):
        self.theme_fixture();self.assertEqual(self.service(TEST_THEME_RC='1').returncode,1)
        self.assertEqual((self.root/'theme-applied').read_text().splitlines(),['apply'])

    def test_default_restores_both_without_apply(self):
        self.theme_fixture();self.active.write_text('default\n')
        self.assertEqual(self.service().returncode,0)
        self.assertEqual(self.applied(),[])
        self.assertEqual((self.root/'restored').read_text(),'restore\n')
        self.assertEqual((self.root/'theme-restored').read_text(),'restore\n')

    def test_disable_and_remove_restore_before_any_apply(self):
        for marker in ('disable','remove'):
            with self.subTest(marker=marker):
                (self.module/marker).touch()
                self.assertEqual(self.service().returncode,0)
                self.assertEqual(self.applied(),[])
                (self.module/marker).unlink()

    def test_restore_failure_bounded_and_journal_retained(self):
        self.active.write_text('default\n')
        journal=self.module/'config/provider-journal';journal.write_text('owned')
        self.assertEqual(self.service(TEST_RESTORE_RC='1').returncode,1)
        self.assertEqual((self.root/'restored').read_text().splitlines(),['restore']*3)
        self.assertEqual(journal.read_text(),'owned')

    def test_singleton_is_owned_before_boot_wait(self):
        self.commands('getprop','[ -s "$MODDIR/.google-font-provider.lock/pid" ] || touch "$TEST_ROOT/unlocked"\necho 1\n')
        self.service();self.assertFalse((self.root/'unlocked').exists())

    def test_cancel_reaps_owned_retry_sleep(self):
        self.active.write_text('default\n')
        self.commands('sleep','echo $$ > "$TEST_ROOT/sleep-pid"\nexec /bin/sleep 30\n')
        p=subprocess.Popen(['sh',str(ROOT/'common/google_font_provider_service.sh')],
            env={**self.env,'TEST_RESTORE_RC':'1'},stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            deadline=time.monotonic()+5
            while not (self.root/'sleep-pid').exists() and time.monotonic()<deadline:time.sleep(.02)
            self.assertTrue((self.root/'sleep-pid').exists())
            pid=int((self.root/'sleep-pid').read_text())
            p.terminate();out,err=p.communicate(timeout=5)
            self.assertEqual(p.returncode,143,err)
            self.assertFalse(Path('/proc',str(pid)).exists())
        finally:
            if p.poll() is None:p.kill();p.communicate(timeout=5)

    def fingerprint(self, paths, pids):
        script = '. "$1"; _gfp_namespace_pids() { cat "$TEST_PIDS"; }; _gfp_fingerprint'
        result = subprocess.run(["sh", "-c", script, "sh",
                                 str(ROOT / "common/google_font_provider_bridge.sh")],
                                env={**self.env, "LUOSHU_PROC_ROOT": str(self.root / "proc"),
                                     "LUOSHU_GOOGLE_FONT_TARGETS": "\n".join(map(str, paths)),
                                     "TEST_PIDS": str(pids)},
                                capture_output=True, text=True, check=True, timeout=5)
        self.assertRegex(result.stdout, r"^[a-f0-9]{64}\n$")
        return result.stdout

    def test_real_fingerprint_catches_cache_inode_and_process_mount_view(self):
        target = self.root / "provider/cache font"
        target.parent.mkdir()
        target.write_bytes(b"original")
        pids = self.root / "pids"
        pids.write_text("10\n")
        nsdir = self.root / "proc/10/ns"
        nsdir.mkdir(parents=True)
        (nsdir / "mnt").symlink_to("mnt:[101]")
        view = self.root / "proc/10/root" / str(target).lstrip("/")
        view.parent.mkdir(parents=True)
        view.write_bytes(b"replaced")
        paths = [target, self.root / "provider/lazy-font"]
        initial = self.fingerprint(paths, pids)
        self.assertEqual(initial, self.fingerprint(paths, pids))
        # Same path/size/timestamps, different inode: atomic GMS cache update.
        replacement = target.with_suffix(".new")
        replacement.write_bytes(target.read_bytes())
        shutil.copystat(target, replacement)
        replacement.replace(target)
        changed = self.fingerprint(paths, pids)
        self.assertNotEqual(initial, changed)
        # Only a target process loses its bind; the root-visible cache is stable.
        alternate = view.with_suffix(".new")
        alternate.write_bytes(view.read_bytes())
        shutil.copystat(view, alternate)
        alternate.replace(view)
        lost_mount = self.fingerprint(paths, pids)
        self.assertNotEqual(changed, lost_mount)
        (nsdir / "mnt").unlink()
        (nsdir / "mnt").symlink_to("mnt:[202]")
        new_namespace = self.fingerprint(paths, pids)
        self.assertNotEqual(lost_mount, new_namespace)
        paths[1].write_bytes(b"downloaded")
        self.assertNotEqual(new_namespace, self.fingerprint(paths, pids))


if __name__ == "__main__":
    unittest.main()
