#!/usr/bin/env python3
"""Exercise late downloads/process changes after the boot discovery window."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
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
