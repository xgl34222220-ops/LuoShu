#!/usr/bin/env python3
"""Font applies must not stall in deep sleep or be killed mid live mount.

Device export 2026-10-19: complete_hyperos lasted 541.7 s of proc uptime but
the outer task supervisor (monotonic clock) only saw 213 s in total: the phone
slept ~475 s. The axes worker then hit its wall-clock 600 s wait limit while the
commit monitor was in live_mount, exited 125, and its supervisor killed the
monitor. These tests run the real shell functions.
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / "common/background_task.sh"
V142 = ROOT / "common/legacy_v14_4/v142_weighted_mix.sh"
RUNTIME = ROOT / "common/legacy_v14_4/font_mix_runtime.sh"
SAFE = ROOT / "common/legacy_v14_4/font_switch_safe.sh"


def function(path: Path, name: str) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    start = lines.index(f"{name}() {{")
    end = lines.index("}", start)
    return "\n".join(lines[start:end + 1]) + "\n"


class WakeLock(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.power = self.root / "power"
        self.power.mkdir()
        (self.power / "wake_lock").write_text("")
        (self.power / "wake_unlock").write_text("")

    def sh(self, script: str, **env):
        return subprocess.run(["sh", "-c", f". '{TASKS}'\n{script}"], capture_output=True, text=True,
                              timeout=30, env=dict(os.environ, LUOSHU_WAKE_LOCK_ROOT=str(self.power), **env))

    def test_bounded_named_lock_is_taken_and_released(self):
        result = self.sh("luoshu_wake_lock_acquire mix_worker 2400 && luoshu_wake_lock_release mix_worker")
        self.assertEqual(0, result.returncode, result.stderr)
        # The kernel takes "name timeout_ns": the lock expires if the holder dies.
        self.assertEqual("luoshu_mix_worker 2400000000000\n", (self.power / "wake_lock").read_text())
        self.assertEqual("luoshu_mix_worker\n", (self.power / "wake_unlock").read_text())

    def test_bad_names_and_missing_interface_are_harmless(self):
        self.assertEqual(2, self.sh("luoshu_wake_lock_acquire 'a b' 10").returncode)
        self.assertEqual(2, self.sh("luoshu_wake_lock_acquire '' 10").returncode)
        self.assertEqual("", (self.power / "wake_lock").read_text())
        missing = self.root / "none"
        result = subprocess.run(["sh", "-c", f". '{TASKS}'\nluoshu_wake_lock_acquire x 5; echo $?; "
                                 "luoshu_wake_lock_release x; echo $?"], capture_output=True, text=True,
                                env=dict(os.environ, LUOSHU_WAKE_LOCK_ROOT=str(missing)), timeout=30)
        self.assertEqual(["1", "0"], result.stdout.split())

    def test_every_long_apply_entry_holds_a_lock(self):
        worker = function(V142, "worker")
        self.assertIn('luoshu_wake_lock_acquire mix_worker "$MIX_WORKER_TIMEOUT"', worker)
        self.assertIn("trap 'luoshu_wake_lock_release mix_worker' EXIT", worker)
        monitor = function(RUNTIME, "monitor_task")
        self.assertIn("luoshu_wake_lock_acquire mix_monitor", monitor)
        self.assertIn("trap 'luoshu_wake_lock_release mix_monitor' EXIT", monitor)
        safe = SAFE.read_text(encoding="utf-8")
        self.assertIn("switch) luoshu_wake_lock_acquire safe_switch 1800", safe)
        self.assertIn("luoshu_wake_lock_release safe_switch", function(SAFE, "safe_exit_cleanup"))


class CommitWaitBudget(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.tasks = self.root / "tasks"
        self.tasks.mkdir()

    def run_wait(self, monitor_seconds: float | None, engine_alive: bool, limit: int):
        monitor = self.tasks / "mix-monitor-t1.pid"
        engine = self.tasks / "mix_worker.pid"
        child = None
        if monitor_seconds is not None:
            child = subprocess.Popen(["sleep", str(monitor_seconds)])
            # Reap like the real supervisor, so the exited pid is really gone.
            threading.Thread(target=child.wait, daemon=True).start()
            monitor.write_text(f"{child.pid}\n")
        holder = None
        if engine_alive:
            holder = subprocess.Popen(["sleep", "30"])
            engine.write_text(f"{holder.pid}\n")
        # Liveness through the cheap pid probe; the scope proof always succeeds.
        script = "\n".join([
            "luoshu_pid_value() { sed -n '1{s/[^0-9].*$//;p;}' \"$1\" 2>/dev/null; }",
            "luoshu_task_pid_alive() { _p=$(luoshu_pid_value \"$1\"); [ -n \"$_p\" ] && kill -0 \"$_p\" 2>/dev/null; }",
            f"luoshu_scope_runner() {{ printf '%s\\n' '{self.root}/runner.sh'; }}",
            function(V142, "_wcc_pid_running"),
            function(V142, "wait_child_cleanup"),
            "wait_child_cleanup t1; echo rc=$?",
        ])
        (self.root / "runner.sh").write_text("exit 0\n")
        started = time.monotonic()
        try:
            result = subprocess.run(["sh", "-c", script], capture_output=True, text=True, timeout=60,
                                    env=dict(os.environ, LUOSHU_TASKS_DIR=str(self.tasks),
                                             LUOSHU_MIX_CHILD_CLEANUP_TIMEOUT=str(limit)))
        finally:
            for process in (child, holder):
                if process:
                    process.kill(); process.wait()
        return result.stdout.strip(), time.monotonic() - started

    def test_never_gives_up_while_the_commit_monitor_runs(self):
        # Budget already exhausted (0 s), but the monitor is still committing.
        output, elapsed = self.run_wait(monitor_seconds=2.5, engine_alive=False, limit=0)
        self.assertEqual("rc=0", output)
        self.assertGreaterEqual(elapsed, 2.0)

    def test_gives_up_on_an_engine_without_a_monitor(self):
        output, elapsed = self.run_wait(monitor_seconds=None, engine_alive=True, limit=1)
        self.assertEqual("rc=124", output)
        self.assertLess(elapsed, 20)

    def test_budget_is_awake_poll_time_not_wall_clock(self):
        body = function(V142, "wait_child_cleanup")
        self.assertNotIn("date +%s", body)
        self.assertRegex(body, re.escape('[ $((_wcc_tries / 5)) -ge "$_wcc_limit" ]'))

    def test_outer_budgets_cover_the_commit_monitor(self):
        source = V142.read_text(encoding="utf-8")
        worker = int(re.search(r'MIX_WORKER_TIMEOUT="\$\{LUOSHU_MIX_WORKER_TIMEOUT:-(\d+)\}"', source).group(1))
        monitor = int(re.search(r'_monitor_timeout="\$\{LUOSHU_MIX_MONITOR_TIMEOUT:-(\d+)\}"',
                                RUNTIME.read_text(encoding="utf-8")).group(1))
        engine = 480 + 15  # font_mix_engine.sh LUOSHU_MIX_TASK_TIMEOUT default + margin
        # prepare (minutes on a phone) + engine + the whole monitor must fit.
        self.assertGreaterEqual(worker, engine + monitor + 15 + 300)
        self.assertNotIn("--timeout 900", source)
        self.assertNotIn("LUOSHU_TASK_TIMEOUT_SECONDS=900", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
