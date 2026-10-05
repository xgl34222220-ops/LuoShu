#!/usr/bin/env python3
"""Run both real cache launchers and prove they retain intent without descendants."""
import os
from pathlib import Path
import select
import shutil
import signal
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


def proc_pid(local_pid):
    """Map Popen's namespace PID into the mounted /proc view used by CI."""
    namespace = os.readlink("/proc/self/ns/pid")
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if os.readlink(entry / "ns/pid") != namespace:
                continue
            status = (entry / "status").read_text().splitlines()
            identifiers = next(line.split()[1:] for line in status if line.startswith("NSpid:"))
            if int(identifiers[-1]) == local_pid:
                return int(entry.name)
        except (OSError, ValueError, StopIteration):
            continue
    raise RuntimeError(f"fixture PID {local_pid} is not visible in /proc")


def live_children(parent):
    """Observe child PPIDs directly; some CI kernels omit task/children."""
    found = []
    namespace = os.readlink("/proc/self/ns/pid")
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            if os.readlink(entry / "ns/pid") != namespace:
                continue
            fields = (entry / "stat").read_text().rsplit(") ", 1)[1].split()
            if int(fields[1]) == parent and fields[0] != "Z":
                found.append(int(entry.name))
        except (OSError, ValueError, IndexError):
            continue
    return found


class CacheLauncherLifecycleTest(unittest.TestCase):
    def run_launcher(self, action, lock=""):
        with tempfile.TemporaryDirectory(prefix="luoshu-cache-launcher-") as temporary:
            module = Path(temporary) / "module"
            common = module / "common"
            common.mkdir(parents=True)
            (module / "config").mkdir()
            (module / "logs").mkdir()
            for name in ("device_font_cache.sh", "device_font_dynamic_guard.sh"):
                shutil.copy2(ROOT / "common" / name, common / name)
            pending = module / "config/device-font-cache-pending.conf"
            original = "state=pending\nfont=Demo\ncacheId=fixture\n"
            pending.write_text(original)
            (module / "config/active_font.conf").write_text("Demo\n")
            if lock:
                directory = module / ".device-font-cache.lock"
                directory.mkdir()
                (directory / "pid").write_text(lock + "\n")
            script = Path(temporary) / "launcher.sh"
            script.write_text(r'''#!/bin/sh
. "$MODDIR/common/device_font_cache.sh"
. "$MODDIR/common/device_font_dynamic_guard.sh"
_dfcache_log() { :; }
_dfpr_module() { printf '%s\n' "$MODDIR"; }
_dfpr_log() { :; }
_dfcache_foreground_idle() { return 0; }
_dfcache_template_key() { printf 'fixture-template\n'; }
_dfcache_source_key() { printf 'fixture-source\n'; }
_dfcache_id() { printf 'fixture\n'; }
_dfcache_run_service_lowpri() {
    printf 'unexpected-service\n' > "$MODDIR/service-started"
    sleep 60
}
case "$1" in
    schedule) device_font_cache_schedule Demo ;;
    autostart) _dfcache_autostart_pending Demo ;;
    boot) _dfpr_launch_pending_cache ;;
    *) exit 2 ;;
esac
printf 'ready\n'
# Keep this exact launching shell alive so /proc records any children it left.
IFS= read -r _fixture_finish
''')
            environment = dict(os.environ, MODDIR=str(module), MODULE_DIR=str(module),
                               LUOSHU_CACHE_AUTOSTART="1")
            process = subprocess.Popen(["sh", str(script), action], env=environment,
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, text=True, start_new_session=True)
            try:
                ready, _, _ = select.select([process.stdout], [], [], 5)
                self.assertTrue(ready, "launcher did not return promptly")
                self.assertEqual(process.stdout.readline().strip(), "ready")
                # Old launchers return before their raw child has run; keep a real
                # process observation instead of relying only on a service marker.
                time.sleep(0.05)
                visible_pid = proc_pid(process.pid)
                children = live_children(visible_pid)
                self.assertEqual(children, [], "launcher left an unowned child")
                self.assertFalse((module / "service-started").exists())
                retained = pending.read_text()
                self.assertIn("state=pending\n", retained)
                self.assertIn("font=Demo\n", retained)
                if action != "schedule":
                    self.assertEqual(retained, original)
                process.stdin.write("finish\n")
                process.stdin.flush()
                self.assertEqual(process.wait(timeout=5), 0)
            finally:
                # Only this isolated fixture's process group is ever signalled.
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.communicate(timeout=2)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.communicate(timeout=2)

    def test_schedule_default_autostart_retains_pending_without_child(self):
        self.run_launcher("schedule")

    def test_autostart_retains_pending_without_waiter(self):
        self.run_launcher("autostart")

    def test_boot_pending_does_not_spawn(self):
        self.run_launcher("boot")

    def test_boot_pending_with_stale_lock_does_not_spawn(self):
        self.run_launcher("boot", "999999999")


if __name__ == "__main__":
    unittest.main()
