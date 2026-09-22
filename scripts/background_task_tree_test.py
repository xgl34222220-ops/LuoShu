#!/usr/bin/env python3
"""Real process tests for cancellation, reparenting and switch-worker signals."""
import os
import json
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]


def alive(pid, proc_id=None):
    try:
        return Path(f"/proc/{proc_id or pid}/stat").read_text().split(") ", 1)[1].split()[0] != "Z"
    except FileNotFoundError:
        return False


class BackgroundTreeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.proc = self.root / "proc"
        self.proc.mkdir()
        # Some executor containers expose a procfs from an outer PID namespace.
        # The workers report their true identities; only the /proc/ps transport
        # is a fixture. Signals, reparenting and process termination remain real.
        ps = self.bin / "ps"
        ps.write_text(f"#!/bin/sh\ncat '{self.root / 'process-tree'}'\n")
        ps.chmod(0o755)
        self.env = {**os.environ, "PATH": f"{self.bin}:{os.environ['PATH']}",
                    "LUOSHU_PROC_ROOT": str(self.proc)}

    def spawn(self, command, **kwargs):
        process = subprocess.Popen(command, start_new_session=True,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kwargs)

        def cleanup():
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=5)

        self.addCleanup(cleanup)
        return process

    def wait_for(self, predicate):
        end = time.monotonic() + 5
        while time.monotonic() < end:
            if predicate():
                return
            time.sleep(0.02)
        self.fail("condition not reached within five seconds")

    def worker_files(self):
        leaf = self.root / "fonttools-worker.py"
        leaf.write_text("import os, signal, time, json\nfrom pathlib import Path\n"
                        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
                        f"Path({str(self.root / 'leaf.pid')!r}).write_text(str(os.getpid()))\n"
                        f"Path({str(self.root / 'leaf.json')!r}).write_text(json.dumps("
                        "[os.getpid(), os.getppid(), os.readlink('/proc/self')]))\n"
                        "while True: time.sleep(0.02)\n")
        middle = self.root / "middle.sh"
        middle.write_text("#!/bin/sh\n"
                          f"printf '%s %s ' \"$$\" \"$PPID\" > '{self.root / 'middle.info'}'\n"
                          f"IFS= read -r stat < /proc/self/stat\nprintf '%s\\n' \"${{stat%% *}}\" >> '{self.root / 'middle.info'}'\n"
                          f"{sys.executable} '{leaf}' &\nwait $!\n")
        manager = self.root / "manager.sh"
        manager.write_text("#!/bin/sh\ntrap 'exit 143' TERM\n"
                           f"printf '%s %s ' \"$$\" \"$PPID\" > '{self.root / 'manager.info'}'\n"
                           f"IFS= read -r stat < /proc/self/stat\nprintf '%s\\n' \"${{stat%% *}}\" >> '{self.root / 'manager.info'}'\n"
                           f"sh '{middle}' &\nwait $!\n")
        return manager

    def snapshot(self):
        self.wait_for(lambda: (self.root / "leaf.json").exists())
        records = [list(map(int, (self.root / f"{name}.info").read_text().split()))
                   for name in ("manager", "middle")]
        leaf = json.loads((self.root / "leaf.json").read_text())
        records.append(leaf)
        for pid, _, proc_id in records:
            folder = self.proc / str(pid)
            folder.mkdir(exist_ok=True)
            (folder / "stat").write_text(Path(f"/proc/{proc_id}/stat").read_text())
        (self.root / "process-tree").write_text("PID PPID\n" + "\n".join(
            f"{pid} {ppid}" for pid, ppid, _ in records))
        return leaf

    def test_kills_term_ignoring_grandchild_after_parent_exits(self):
        manager = self.worker_files()
        worker = self.spawn(["sh", str(manager)])
        sentinel = self.spawn([sys.executable, "-c", "import time; time.sleep(60)"])
        leaf, _, proc_id = self.snapshot()
        subprocess.run(["sh", "-c", '. "$1"; luoshu_terminate_task_tree "$2"', "sh",
                        str(ROOT / "common/background_task.sh"), str(worker.pid)],
                       env=self.env, check=True, timeout=5)
        self.wait_for(lambda: not alive(leaf, proc_id))
        self.assertIsNotNone(worker.poll())
        self.assertIsNone(sentinel.poll(), "cancellation killed an unrelated process")

    def test_old_boot_sidecar_does_not_kill_reused_pid(self):
        sentinel = self.spawn([sys.executable, "-c", "import time; time.sleep(60)", "old-task"])
        pidfile = self.root / "task.pid"
        pidfile.write_text(str(sentinel.pid))
        Path(str(pidfile) + ".task").write_text("old-task")
        Path(str(pidfile) + ".boot").write_text("previous-boot")
        subprocess.run(["sh", "-c", '. "$1"; luoshu_stop_task_pid "$2"', "sh",
                        str(ROOT / "common/background_task.sh"), str(pidfile)], check=True, timeout=5)
        self.assertIsNone(sentinel.poll())
        self.assertFalse(pidfile.exists())

    def test_switch_worker_term_exits_and_cleans_nested_generator(self):
        manager = self.worker_files()
        module = self.root / "module"
        (module / "common").mkdir(parents=True)
        (module / "config").mkdir()
        (module / "common/background_task.sh").symlink_to(ROOT / "common/background_task.sh")
        worker = self.spawn(["sh", str(ROOT / "common/font_switch_task.sh"),
                             "run", "signal-task", "custom-font", "1"],
                            env={**self.env, "MODDIR": str(module), "LUOSHU_FONT_MANAGER": str(manager)})
        leaf, _, proc_id = self.snapshot()
        worker.terminate()
        self.assertEqual(worker.wait(timeout=5), 143)
        self.wait_for(lambda: not alive(leaf, proc_id))
        task = (module / "config/switch_task.conf").read_text()
        self.assertIn("state=failed\n", task)
        self.assertIn("task=signal-task\n", task)
        self.assertFalse(list((module / "config").glob("*.progress.*")))

    def test_quiesce_font_workers_kills_registered_transients_only(self):
        module = self.root / "quiesce-module"
        config = module / "config"
        config.mkdir(parents=True)
        task = "axes-cleanup"
        worker = self.spawn([sys.executable, "-c", "import time; time.sleep(60)", task])
        unrelated = self.spawn([sys.executable, "-c", "import time; time.sleep(60)", "unrelated-sentinel"])
        pidfile = config / "axes_worker.pid"
        pidfile.write_text(str(worker.pid))
        Path(str(pidfile) + ".task").write_text(task)

        subprocess.run(
            ["sh", "-c", '. "$1"; luoshu_quiesce_font_workers "$2" "$"', "sh",
             str(ROOT / "common/background_task.sh"), str(module)],
            env=os.environ.copy(), check=True, timeout=5,
        )
        self.wait_for(lambda: worker.poll() is not None)
        self.assertIsNone(unrelated.poll(), "quiesce killed an unrelated process")
        self.assertFalse(pidfile.exists())
        self.assertFalse(Path(str(pidfile) + ".task").exists())

    def test_provider_service_term_reaps_active_generator_and_releases_singleton(self):
        manager = self.worker_files()
        module = self.root / "module"
        (module / "common").mkdir(parents=True)
        (module / "config").mkdir()
        (module / "config/active_font.conf").write_text("custom\n")
        for name in ("background_task.sh", "font_switch_lock.sh"):
            (module / "common" / name).symlink_to(ROOT / "common" / name)
        (module / "common/google_font_provider_bridge.sh").write_text(
            f'case "$1" in fingerprint) echo current;; apply) exec sh "{manager}";; esac\n')
        getprop = self.bin / "getprop"
        getprop.write_text("#!/bin/sh\necho 1\n")
        getprop.chmod(0o755)
        service = self.spawn(["sh", str(ROOT / "common/google_font_provider_service.sh")],
                             env={**self.env, "MODDIR": str(module)})
        leaf, _, proc_id = self.snapshot()
        service.terminate()
        self.assertEqual(service.wait(timeout=5), 143)
        self.wait_for(lambda: not alive(leaf, proc_id))
        self.assertFalse((module / ".google-font-provider.lock").exists())


if __name__ == "__main__":
    unittest.main()
