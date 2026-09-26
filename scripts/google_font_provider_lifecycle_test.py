#!/usr/bin/env python3
"""Exercise late downloads/process changes after the boot discovery window."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ProviderLifecycleTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.module = self.root / "module"
        (self.module / "common").mkdir(parents=True)
        (self.module / "config").mkdir()
        self.active = self.module / "config/active_font.conf"
        self.active.write_text("custom\n")
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.marker = self.root / "applied"
        self.snapshot = self.root / "snapshot"
        self.snapshot.write_text("boot-cache-and-namespace\n")
        self.commands("getprop", "echo 1\n")
        shutil.copyfile(ROOT / "common/font_switch_lock.sh",
                        self.module / "common/font_switch_lock.sh")
        (self.module / "common/google_font_provider_bridge.sh").write_text('''
case "$1" in
    fingerprint) cat "$TEST_SNAPSHOT" ;;
    apply)
        printf '%s|%s\\n' "$(cat "$TEST_SNAPSHOT")" "${LUOSHU_GOOGLE_FONT_ALLOW_RESTART:-1}" >> "$TEST_APPLIED"
        if [ -s "$TEST_ROOT/during-apply" ]; then
            cat "$TEST_ROOT/during-apply" > "$TEST_SNAPSHOT"
            rm "$TEST_ROOT/during-apply"
        fi
        exit "${TEST_APPLY_RC:-0}"
        ;;
esac
''')
        self.env = {**os.environ, "MODDIR": str(self.module),
                    "PATH": f"{self.bin}:{os.environ['PATH']}",
                    "TEST_ROOT": str(self.root), "TEST_SNAPSHOT": str(self.snapshot),
                    "TEST_APPLIED": str(self.marker), "LUOSHU_GOOGLE_FONT_RETRIES": "1",
                    "LUOSHU_GOOGLE_FONT_WATCH_INTERVAL": "30"}

    def commands(self, name, text):
        path = self.bin / name
        path.write_text("#!/bin/sh\n" + text)
        path.chmod(0o755)

    def service(self, cycles, sleep_actions=":", **env):
        self.commands("sleep", '''
count=$(cat "$TEST_ROOT/ticks" 2>/dev/null || echo 0)
count=$((count + 1))
printf '%s\\n' "$count" > "$TEST_ROOT/ticks"
''' + sleep_actions + "\n")
        subprocess.run(["sh", str(ROOT / "common/google_font_provider_service.sh")],
                       env={**self.env, "LUOSHU_GOOGLE_FONT_WATCH_CYCLES": str(cycles), **env},
                       capture_output=True, text=True, check=True, timeout=10)
        self.assertFalse((self.module / ".google-font-provider.lock").exists())
        return self.marker.read_text().splitlines() if self.marker.exists() else []

    def test_late_download_and_restarted_provider_repaired_after_boot_window(self):
        applied = self.service(4, '''
case "$count" in
    1) printf 'late-downloaded-bold\\n' > "$TEST_SNAPSHOT" ;;
    3) printf 'new-gms-namespace\\n' > "$TEST_SNAPSHOT" ;;
esac
''')
        self.assertEqual(applied, ["boot-cache-and-namespace|1",
                                   "late-downloaded-bold|0", "new-gms-namespace|0"])

    def test_idle_watch_does_not_reapply_fonts(self):
        self.assertEqual(self.service(20), ["boot-cache-and-namespace|1"])

    def theme_fixture(self):
        (self.root / 'theme-snapshot').write_text('theme-one\n')
        (self.module / 'common/dynamic_font_route_bridge.sh').write_text('''
case "$1" in
    fingerprint) cat "$TEST_ROOT/theme-snapshot" ;;
    apply)
        cat "$TEST_ROOT/theme-snapshot" >> "$TEST_ROOT/theme-applied"
        exit "${TEST_THEME_RC:-0}"
        ;;
    restore)
        echo restored >> "$TEST_ROOT/theme-restored"
        count=$(wc -l < "$TEST_ROOT/theme-restored")
        [ "$count" -gt "${TEST_THEME_RESTORE_FAILURES:-0}" ] || exit 1
        ;;
esac
''')

    def test_theme_route_change_is_watched_when_google_has_no_fonts(self):
        self.theme_fixture()
        self.service(3, '''
if [ "$count" = 2 ]; then echo theme-two > "$TEST_ROOT/theme-snapshot"; fi
''', TEST_APPLY_RC='2')
        self.assertEqual((self.root / 'theme-applied').read_text().splitlines(),
                         ['theme-one', 'theme-two'])

    def test_idle_theme_does_not_start_repeated_builds(self):
        self.theme_fixture()
        self.service(20)
        self.assertEqual((self.root / 'theme-applied').read_text().splitlines(), ['theme-one'])

    def test_legacy_theme_adapter_only_restores_before_inventory_routes_apply(self):
        self.theme_fixture()
        journal = self.module / 'config/hyperos-theme-font-namespaces.conf'
        journal.write_text('old-owned-mount\n')
        (self.module / 'common/hyperos_theme_font_bridge.sh').write_text('''
case "$1" in
    restore)
        echo restore >> "$TEST_ROOT/legacy-events"
        rm -f "$MODDIR/config/hyperos-theme-font-namespaces.conf"
        ;;
    *) echo forbidden >> "$TEST_ROOT/legacy-events"; exit 99 ;;
esac
''')
        self.service(4)
        self.assertEqual((self.root / 'legacy-events').read_text().splitlines(), ['restore'])
        self.assertEqual((self.root / 'theme-applied').read_text().splitlines(), ['theme-one'])

    def test_theme_failure_gets_backoff_even_when_google_succeeds(self):
        self.theme_fixture()
        self.service(11, TEST_THEME_RC='1')
        self.assertEqual((self.root / 'theme-applied').read_text().splitlines(),
                         ['theme-one', 'theme-one'])

    def test_restoring_default_releases_owned_theme_mounts(self):
        self.theme_fixture()
        self.service(4, '''
if [ "$count" = 1 ]; then echo default > "$MODDIR/config/active_font.conf"; fi
''')
        self.assertEqual((self.root / 'theme-restored').read_text(), 'restored\n')
        self.assertEqual((self.root / 'theme-applied').read_text().splitlines(), ['theme-one'])

    def test_theme_restore_retries_transient_failure_then_exits(self):
        self.theme_fixture()
        self.service(4, '''
if [ "$count" = 1 ]; then echo default > "$MODDIR/config/active_font.conf"; fi
''', TEST_THEME_RESTORE_FAILURES='2')
        self.assertEqual((self.root / 'theme-restored').read_text().splitlines(),
                         ['restored'] * 3)
        self.assertEqual((self.root / 'theme-applied').read_text().splitlines(), ['theme-one'])

    def test_default_disable_and_remove_report_bounded_restore_failure(self):
        self.theme_fixture()
        journal = self.module / 'config/dynamic-font-routes/test/namespaces.conf'
        journal.parent.mkdir(parents=True)
        for stop in ('default', 'disable', 'remove'):
            with self.subTest(stop=stop):
                self.active.write_text('custom\n')
                for name in ('disable', 'remove'):
                    (self.module / name).unlink(missing_ok=True)
                for name in ('ticks', 'theme-restored', 'theme-applied'):
                    (self.root / name).unlink(missing_ok=True)
                journal.write_text('mnt:[123]|owned-font-inode\n')
                action = ('echo default > "$MODDIR/config/active_font.conf"'
                          if stop == 'default' else f'touch "$MODDIR/{stop}"')
                with self.assertRaises(subprocess.CalledProcessError) as failed:
                    self.service(20, action, TEST_THEME_RESTORE_FAILURES='99')
                self.assertEqual(failed.exception.returncode, 1)
                self.assertEqual((self.root / 'theme-restored').read_text().splitlines(),
                                 ['restored'] * 3)
                self.assertEqual((self.root / 'theme-applied').read_text().splitlines(), ['theme-one'])
                self.assertEqual(journal.read_text(), 'mnt:[123]|owned-font-inode\n')
                self.assertIn('attempt 3/3',
                              (self.module / 'logs/google-font-provider.log').read_text())
                self.assertFalse((self.module / '.google-font-provider.lock').exists())

    def test_removed_module_does_not_recreate_cleanup_files(self):
        self.theme_fixture()
        self.service(4, 'rm -rf "$MODDIR"')
        self.assertFalse(self.module.exists())
        self.assertFalse((self.root / 'theme-restored').exists())

    def test_theme_restore_retry_pause_is_cancelled_with_service(self):
        self.theme_fixture()
        self.active.write_text('default\n')
        self.commands('sleep', '''
echo $$ > "$TEST_ROOT/retry-sleep-pid"
exec /bin/sleep 30
''')
        process = subprocess.Popen(
            ['sh', str(ROOT / 'common/google_font_provider_service.sh')],
            env={**self.env, 'TEST_THEME_RESTORE_FAILURES': '99'},
            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            pid_file = self.root / 'retry-sleep-pid'
            deadline = time.monotonic() + 5
            while not pid_file.exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(pid_file.exists(), 'service did not reach restore retry pause')
            child_pid = int(pid_file.read_text())
            process.terminate()
            process.communicate(timeout=5)
            self.assertEqual(process.returncode, 143)
            with self.assertRaises(ProcessLookupError):
                os.kill(child_pid, 0)
            self.assertFalse((self.module / '.google-font-provider.lock').exists())
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)

    def test_idle_boot_discovery_does_not_apply_twenty_four_times(self):
        self.assertEqual(self.service(0, LUOSHU_GOOGLE_FONT_RETRIES="24"),
                         ["boot-cache-and-namespace|1"])

    def test_boot_discovery_still_catches_new_download_after_initial_success(self):
        self.assertEqual(self.service(0, '''
if [ "$count" = 12 ]; then printf 'late-boot-download\\n' > "$TEST_SNAPSHOT"; fi
''', LUOSHU_GOOGLE_FONT_RETRIES="24"),
                         ["boot-cache-and-namespace|1", "late-boot-download|1"])

    def test_stable_boot_failure_has_thirty_second_backoff(self):
        self.assertEqual(self.service(0, LUOSHU_GOOGLE_FONT_RETRIES="24", TEST_APPLY_RC="1"),
                         ["boot-cache-and-namespace|1"] * 4)

    def test_singleton_is_owned_before_boot_wait_starts(self):
        self.commands("getprop", '''
[ -s "$MODDIR/.google-font-provider.lock/pid" ] || touch "$TEST_ROOT/unlocked-boot-wait"
echo 1
''')
        self.assertEqual(self.service(0), ["boot-cache-and-namespace|1"])
        self.assertFalse((self.root / "unlocked-boot-wait").exists())

    def test_persistent_error_log_rotates_and_retains_latest_event(self):
        logs = self.module / "logs"
        logs.mkdir()
        log = logs / "google-font-provider.log"
        previous = b"x" * 1048576
        log.write_bytes(previous)
        subprocess.run(["sh", "-c", '. "$1"; _gfp_log repaired', "sh",
                        str(ROOT / "common/google_font_provider_bridge.sh")],
                       env=self.env, check=True, capture_output=True, timeout=5)
        self.assertEqual(Path(str(log) + ".1").read_bytes(), previous)
        self.assertIn("repaired", log.read_text())
        self.assertLess(log.stat().st_size, 1024)

    def test_no_downloaded_files_does_not_launch_python_or_scan_processes(self):
        script = '''. "$1"
_gfp_targets() { :; }
_gfp_python() { echo unexpected-python >&2; return 91; }
_gfp_namespace_pids() { echo unexpected-process-scan >&2; return 92; }
_gfp_apply_once
rc=$?
[ "$rc" = 2 ] || exit "$rc"
_gfp_fingerprint
'''
        result = subprocess.run(["sh", "-c", script, "sh",
                                 str(ROOT / "common/google_font_provider_bridge.sh")],
                                env=self.env, capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertRegex(result.stdout, r"^[a-f0-9]{64}\n$")

    def test_partial_failure_retries_at_five_minutes_not_each_watch(self):
        self.assertEqual(self.service(11, TEST_APPLY_RC="1"),
                         ["boot-cache-and-namespace|1", "boot-cache-and-namespace|0"])

    def test_no_download_yet_is_not_a_repeated_failure(self):
        self.assertEqual(self.service(11, TEST_APPLY_RC="2"), ["boot-cache-and-namespace|1"])

    def test_new_download_during_apply_is_not_hidden_by_post_apply_snapshot(self):
        applied = self.service(3, '''
if [ "$count" = 1 ]; then
    printf 'first-late-font\\n' > "$TEST_SNAPSHOT"
    printf 'arrived-during-repair\\n' > "$TEST_ROOT/during-apply"
fi
''')
        self.assertEqual(applied, ["boot-cache-and-namespace|1", "first-late-font|0",
                                   "arrived-during-repair|0"])

    def test_last_boot_apply_does_not_mask_late_download(self):
        (self.root / "during-apply").write_text("arrived-during-boot-apply\n")
        self.assertEqual(self.service(2), ["boot-cache-and-namespace|1",
                                           "arrived-during-boot-apply|0"])

    def test_interrupted_apply_also_retries(self):
        self.assertEqual(self.service(11, TEST_APPLY_RC="137"),
                         ["boot-cache-and-namespace|1", "boot-cache-and-namespace|0"])

    def test_default_or_disabled_module_stops_watch_before_repair(self):
        for stop in ("default", "disable", "remove"):
            with self.subTest(stop=stop):
                self.active.write_text("custom\n")
                self.marker.unlink(missing_ok=True)
                for name in ("disable", "remove"):
                    (self.module / name).unlink(missing_ok=True)
                action = ('printf "default\\n" > "$MODDIR/config/active_font.conf"'
                          if stop == "default" else f'touch "$MODDIR/{stop}"')
                self.assertEqual(self.service(3, action), ["boot-cache-and-namespace|1"])

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
