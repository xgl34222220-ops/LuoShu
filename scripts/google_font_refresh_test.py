#!/usr/bin/env python3
"""Exercise deferred font-FD refresh with the real bridge and a fixture procfs."""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class GoogleFontRefreshTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.module = self.root / "module"
        (self.module / "config").mkdir(parents=True)
        self.active = self.module / "config/active_font.conf"
        self.active.write_text("custom\n")
        self.queue = self.module / "config/google-font-refresh-pending.conf"
        self.proc = self.root / "proc"
        self.proc.mkdir()
        self.boot_id = self.proc / "sys/kernel/random/boot_id"
        self.boot_id.parent.mkdir(parents=True)
        self.boot_id.write_text("fixture-boot-one\n")
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.now = self.root / "now"
        self.now.write_text("1000\n")
        self.old_font = self.root / "old-font.ttf"
        self.old_font.write_bytes(b"old downloaded font bytes" * 128)
        old_stat = self.old_font.stat()
        self.identity = f"{old_stat.st_dev}:{old_stat.st_ino}"
        self.am_log = self.root / "am.log"
        self.timeout_log = self.root / "timeout.log"
        self.command("date", '''
if [ "$1" = +%s ]; then cat "$TEST_ROOT/now"; else exec /bin/date "$@"; fi
''')
        self.command("timeout", '''
printf '%s\\n' "$*" >> "$TEST_ROOT/timeout.log"
[ "$1" = 3 ] || exit 97
shift
exec "$@"
''')
        # ActivityManager is the fixture boundary: foreground keeps its PID;
        # the background case removes only this fake user's matching package.
        self.command("am", '''
printf '%s\\n' "$*" >> "$TEST_ROOT/am.log"
[ "$#" = 4 ] && [ "$1" = kill ] && [ "$2" = --user ] || exit 98
[ "${TEST_AM_BEHAVIOR:-foreground}" = background ] || exit 0
for process in "$LUOSHU_PROC_ROOT"/[0-9]*; do
    [ -d "$process" ] || continue
    name=$(tr '\\000' '\\n' < "$process/cmdline" | head -n1)
    name=${name%%:*}
    uid=$(awk '/^Uid:/ {print $2; exit}' "$process/status")
    [ "$name" = "$4" ] && [ "$((uid / 100000))" = "$3" ] || continue
    rm -rf "$process"
done
''')
        self.env = {
            **os.environ,
            "MODDIR": str(self.module),
            "LUOSHU_PROC_ROOT": str(self.proc),
            "TEST_ROOT": str(self.root),
            "PATH": f"{self.bin}:{os.environ['PATH']}",
        }

    def command(self, name, body):
        path = self.bin / name
        path.write_text("#!/bin/sh\n" + body)
        path.chmod(0o755)

    def shell(self, commands, **env):
        bridge = shlex.quote(str(ROOT / "common/google_font_provider_bridge.sh"))
        result = subprocess.run(
            ["sh", "-c", f". {bridge}\n{commands}"],
            env={**self.env, **env}, capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def process(self, pid=101, package="com.android.chrome", uid=210123,
                start=8765, fd=True, mapped=False):
        directory = self.proc / str(pid)
        directory.mkdir(exist_ok=True)
        (directory / "fd").mkdir(exist_ok=True)
        (directory / "cmdline").write_bytes(package.encode() + b"\0--fixture\0")
        (directory / "status").write_text(f"Name:\tchrome\nUid:\t{uid}\t{uid}\t{uid}\t{uid}\n")
        self.process_start(pid, start)
        (directory / "maps").write_text("")
        if fd:
            (directory / "fd/7").symlink_to(self.old_font)
        if mapped:
            self.map_font(pid)
        return directory

    def process_start(self, pid, start):
        # Field 22 is starttime. The comm includes whitespace and a close paren,
        # as real /proc stat parsing must not split at its first close paren.
        tail = ["S"] + ["0"] * 18 + [str(start)] + ["0"] * 3
        (self.proc / str(pid) / "stat").write_text(
            f"{pid} (font worker) fixture) " + " ".join(tail) + "\n")

    def map_font(self, pid, other_device=False):
        font_stat = self.old_font.stat()
        major = os.major(font_stat.st_dev) + int(other_device)
        minor = os.minor(font_stat.st_dev)
        (self.proc / str(pid) / "maps").write_text(
            f"100000-101000 r--p 00000000 {major:02x}:{minor:02x} "
            f"{font_stat.st_ino} {self.old_font} (deleted)\n")

    def enqueue(self, *pids):
        self.shell("\n".join(
            f"_gfp_queue_refresh {pid} {shlex.quote(self.identity)}" for pid in pids))

    def refresh(self, **env):
        self.shell("_gfp_refresh_consumers", **env)

    def queued(self):
        return self.queue.read_text().splitlines() if self.queue.exists() else []

    def calls(self):
        return self.am_log.read_text().splitlines() if self.am_log.exists() else []

    def shared_namespace(self, *pids):
        view = self.root / "namespace-root"
        destination = view / str(self.old_font).lstrip("/")
        destination.parent.mkdir(parents=True)
        destination.symlink_to(self.old_font)
        for pid in pids:
            process = self.proc / str(pid)
            (process / "ns").mkdir()
            (process / "ns/mnt").symlink_to("mnt:[93001]")
            (process / "root").symlink_to(view)
        return destination

    def apply_provider_fixture(self):
        # Font recognition/generation and kernel mount are the boundaries here.
        # Enumeration, namespace deduplication, mount journaling, queue creation
        # and live FD matching all execute the production shell unchanged.
        self.command("pidof", "exit 1\n")
        return self.shell('''
_gfp_inspect_targets() {
    printf '%s\\t400\\n' "$TEST_ROOT/old-font.ttf" > "$2"
}
_gfp_source_for_weight() { printf '%s\\n' "$TEST_ROOT/clone.ttf"; }
_gfp_build_clone() { printf '%s\\n' "$TEST_ROOT/clone.ttf"; }
_gfp_mount_in_pid() {
    printf '%s\\n' "$1" >> "$TEST_ROOT/mount-pids"
    ln -sfn "$2" "$LUOSHU_PROC_ROOT/$1/root$3" || return 1
    _gfp_mount_mode=plain
}
_gfp_apply_once || exit $?
_gfp_refresh_consumers
''', LUOSHU_GOOGLE_FONT_TARGETS=str(self.old_font))

    def test_changed_view_without_old_descriptors_or_mappings_needs_no_restart(self):
        self.process(fd=False)
        self.enqueue(101)
        self.assertEqual(len(self.queued()), 1)
        self.refresh()
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.queued(), [])

    def test_exact_old_fd_refreshes_only_the_confirmed_android_user(self):
        self.process(package="com.android.chrome:privileged_process0", uid=210123)
        self.enqueue(101)
        self.refresh()
        self.assertEqual(self.calls(), ["kill --user 2 com.android.chrome"])
        self.assertEqual(self.timeout_log.read_text(), "3 am kill --user 2 com.android.chrome\n")
        self.assertEqual(len(self.queued()), 1, "foreground consumer must remain pending")

    def test_core_services_and_unrelated_apps_are_never_enqueued(self):
        names = ["com.google.android.gms", "com.google.android.gms.persistent",
                 "com.google.android.gms:unstable", "com.google.android.webview",
                 "zygote64", "system_server", "com.tencent.mobileqq"]
        pids = []
        for pid, name in enumerate(names, 200):
            self.process(pid, name)
            pids.append(pid)
        self.process(299, "com.android.chrome", uid=1000)
        self.enqueue(*pids, 299)
        self.refresh()
        self.assertEqual(self.queued(), [])
        self.assertEqual(self.calls(), [])

    def test_foreground_survives_and_background_refresh_retries_after_sixty_seconds(self):
        process = self.process()
        self.enqueue(101)
        self.refresh()
        self.assertTrue(process.exists())
        self.assertEqual(len(self.calls()), 1)
        self.now.write_text("1059\n")
        self.refresh(TEST_AM_BEHAVIOR="background")
        self.assertTrue(process.exists())
        self.assertEqual(len(self.calls()), 1)
        self.now.write_text("1060\n")
        self.refresh(TEST_AM_BEHAVIOR="background")
        self.assertFalse(process.exists())
        self.assertEqual(self.calls(), ["kill --user 2 com.android.chrome"] * 2)
        self.assertEqual(self.queued(), [])

    def test_reused_pid_is_discarded_without_refresh(self):
        self.process()
        self.enqueue(101)
        self.process_start(101, 8766)
        self.refresh()
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.queued(), [])

    def test_same_pid_and_start_time_from_another_boot_are_discarded(self):
        self.process()
        self.enqueue(101)
        self.assertEqual(Path(str(self.queue) + ".boot").read_text(), "fixture-boot-one\n")
        self.boot_id.write_text("fixture-boot-two\n")
        self.refresh()
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.queued(), [])

    def test_fresh_enqueue_after_reboot_drops_the_previous_boot_queue(self):
        self.process(101)
        self.process(102, "com.google.android.youtube")
        self.enqueue(101)
        self.boot_id.write_text("fixture-boot-two\n")
        self.enqueue(102)
        self.assertEqual(len(self.queued()), 1)
        self.assertTrue(self.queued()[0].startswith("102|"))
        self.refresh()
        self.assertEqual(self.calls(), ["kill --user 2 com.google.android.youtube"])

    def test_pid_whose_package_changed_is_discarded(self):
        directory = self.process()
        self.enqueue(101)
        (directory / "cmdline").write_bytes(b"com.google.android.youtube\0")
        self.refresh()
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.queued(), [])

    def test_closed_fd_with_old_font_still_mapped_needs_refresh(self):
        self.process(fd=False, mapped=True)
        self.enqueue(101)
        self.refresh()
        self.assertEqual(self.calls(), ["kill --user 2 com.android.chrome"])

    def test_same_inode_number_on_a_different_filesystem_is_not_a_match(self):
        self.process(fd=False)
        self.map_font(101, other_device=True)
        self.enqueue(101)
        self.refresh()
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.queued(), [])

    def test_default_disable_and_remove_clear_pending_without_touching_apps(self):
        self.process()
        for stop in ("default", "disable", "remove"):
            with self.subTest(stop=stop):
                self.active.write_text("custom\n")
                for name in ("disable", "remove"):
                    (self.module / name).unlink(missing_ok=True)
                self.enqueue(101)
                if stop == "default":
                    self.active.write_text("default\n")
                else:
                    (self.module / stop).touch()
                self.refresh()
                self.assertEqual(self.calls(), [])
                self.assertEqual(self.queued(), [])
                self.assertFalse(self.queue.exists())
                self.assertFalse(Path(str(self.queue) + ".boot").exists())

    def test_exited_process_is_removed_from_pending(self):
        directory = self.process()
        self.enqueue(101)
        shutil.rmtree(directory)
        self.refresh()
        self.assertEqual(self.calls(), [])
        self.assertEqual(self.queued(), [])

    def test_refresh_budget_is_four_bounded_am_calls_per_pass(self):
        for pid in range(101, 107):
            self.process(pid, f"com.google.android.fixture{pid}")
        self.enqueue(*range(101, 107))
        self.refresh()
        self.assertEqual(len(self.calls()), 4)
        self.assertEqual(len(self.queued()), 6)
        self.refresh()
        self.assertEqual(len(self.calls()), 6, "unattempted entries must not be starved")
        self.refresh()
        self.assertEqual(len(self.calls()), 6, "attempted entries must respect cooldown")
        self.assertTrue(all(line.startswith("3 am kill --user 2 ")
                            for line in self.timeout_log.read_text().splitlines()))

    def test_duplicate_font_identity_is_queued_and_refreshed_once(self):
        self.process()
        self.enqueue(101, 101, 101)
        self.assertEqual(len(self.queued()), 1)
        self.refresh()
        self.assertEqual(len(self.calls()), 1)

    def test_consumer_that_releases_the_old_fd_no_longer_needs_refresh(self):
        directory = self.process()
        self.enqueue(101)
        self.refresh()
        (directory / "fd/7").unlink()
        self.now.write_text("1060\n")
        self.refresh()
        self.assertEqual(len(self.calls()), 1)
        self.assertEqual(self.queued(), [])

    def test_shared_namespace_zygote_representative_does_not_hide_chrome_consumer(self):
        self.process(100, "zygote64", uid=0, fd=False)
        self.process(101)
        self.shared_namespace(100, 101)
        (self.root / "clone.ttf").write_bytes(b"custom font bytes" * 128)
        self.apply_provider_fixture()
        self.assertEqual((self.root / "mount-pids").read_text(), "100\n")
        self.assertEqual(self.calls(), ["kill --user 2 com.android.chrome"])
        self.assertTrue((self.proc / "100").exists())

    def test_already_mounted_clone_still_refreshes_old_downloaded_font_fd(self):
        self.process(100, "zygote64", uid=0, fd=False)
        self.process(101)
        destination = self.shared_namespace(100, 101)
        cache = self.module / "config/google-font-provider"
        cache.mkdir()
        clone = self.root / "clone.ttf"
        clone.write_bytes(b"custom font bytes" * 128)
        destination.unlink()
        destination.symlink_to(clone)
        clone_stat = clone.stat()
        mounted_identity = f"{clone_stat.st_dev}:{clone_stat.st_ino}:{clone_stat.st_size}"
        (self.module / "config/google-font-provider-namespaces.conf").write_text(
            f"mnt:[93001]|{self.old_font}|{mounted_identity}|{clone}\n")
        self.apply_provider_fixture()
        self.assertFalse((self.root / "mount-pids").exists(), "existing owned bind must be reused")
        self.assertEqual(self.calls(), ["kill --user 2 com.android.chrome"])

    def test_original_identity_from_state_survives_root_target_already_being_a_clone(self):
        self.process(100, "zygote64", uid=0, fd=False)
        chrome = self.process(101)
        destination = self.shared_namespace(100, 101)
        cache = self.module / "config/google-font-provider"
        cache.mkdir()
        clone = self.root / "clone.ttf"
        clone.write_bytes(b"custom font bytes" * 128)
        # A real descriptor keeps its inode after pathname replacement. Keep
        # that inode via a hardlink in this fake procfs, then replace the path.
        held_inode = self.root / "held-old-inode"
        os.link(self.old_font, held_inode)
        (chrome / "fd/7").unlink()
        (chrome / "fd/7").symlink_to(held_inode)
        self.old_font.unlink()
        self.old_font.symlink_to(clone)
        destination.unlink()
        destination.symlink_to(clone)
        clone_stat = clone.stat()
        mounted_identity = f"{clone_stat.st_dev}:{clone_stat.st_ino}:{clone_stat.st_size}"
        (self.module / "config/google-font-provider-namespaces.conf").write_text(
            f"mnt:[93001]|{self.old_font}|{mounted_identity}|{clone}\n")
        (self.module / "config/google-font-provider-mounts.conf").write_text(
            f"{self.old_font}|{clone}|original-hash|clone-hash|source-hash|400|provider-v3|{self.identity}\n")
        self.apply_provider_fixture()
        self.assertFalse((self.root / "mount-pids").exists())
        self.assertEqual(self.calls(), ["kill --user 2 com.android.chrome"])


if __name__ == "__main__":
    unittest.main()
