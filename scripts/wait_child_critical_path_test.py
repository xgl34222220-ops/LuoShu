#!/usr/bin/env python3
"""worker/wait_child_cleanup: what it waits for, and its own share of the time.

Device exports 2026-10-22 (HyperOS OS3.0 47.5/48.3 s, ColorOS V17 18.9/25.1 s,
result=0 terminated=0): the axes worker enters wait_child_cleanup as soon as
the base engine reports success after local_commit, but the commit monitor
(font_mix_runtime.sh monitor -> mix_router.sh finalize) still runs
finalize_lock, complete_hyperos/complete_coloros, next_commit and live_mount.
The wait overlaps that finalize work for all but ~0.8-1.3 s, and the exported
totalPhaseMs counted it twice (114 s for a 71 s apply). These tests run the
real shell functions and the real diagnostic parser.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
V142 = ROOT / "common/legacy_v14_4/v142_weighted_mix.sh"
RUNTIME = ROOT / "common/legacy_v14_4/font_mix_runtime.sh"
LIVE = ROOT / "common/font_live_switch.sh"
sys.path.insert(0, str(ROOT / "common"))
import font_coverage_locator as locator  # noqa: E402


def function(path: Path, name: str) -> str:
    lines = path.read_text(encoding="utf-8").splitlines()
    start = lines.index(f"{name}() {{")
    end = lines.index("}", start)
    return "\n".join(lines[start:end + 1]) + "\n"


def reaped_sleeper(seconds: float) -> tuple[subprocess.Popen, dict]:
    """A child that is really gone (reaped) when it ends, like a supervisor."""
    process = subprocess.Popen(["sleep", str(seconds)])
    ended: dict = {}

    def reap():
        process.wait()
        ended["at"] = time.monotonic()
    threading.Thread(target=reap, daemon=True).start()
    return process, ended


class Harness(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="luoshu-wait-child-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.tasks = self.root / "tasks"
        self.tasks.mkdir()
        self.probes = self.root / "probes"
        self.probes.write_text("")
        self.calls = self.root / "runner-calls"
        self.calls.write_text("")

    def runner(self, fail_on: str = "") -> Path:
        runner = self.root / "runner.sh"
        runner.write_text("#!/bin/sh\n"
                          f"printf '%s\\n' \"$*\" >> '{self.calls}'\n"
                          + (f"case \"$2\" in *{fail_on}*) exit 1 ;; esac\n" if fail_on else "")
                          + "exit 0\n")
        return runner

    def stubs(self, runner: Path, alive: str) -> str:
        return (
            "set +e\n"
            f"LUOSHU_TASKS_DIR='{self.tasks}'\n"
            f"luoshu_scope_runner() {{ printf '%s\\n' '{runner}'; }}\n"
            "luoshu_pid_value() { sed -n '1{s/[^0-9].*$//;p;}' \"$1\" 2>/dev/null; }\n"
            "luoshu_task_pid_alive() {\n"
            f"    printf '%s\\n' \"$1\" >> '{self.probes}'\n"
            f"{alive}\n"
            "}\n")

    def probe_count(self) -> int:
        return len(self.probes.read_text().splitlines())


class WaitChildCleanupFastPath(Harness):
    KILL0 = "    _p=$(luoshu_pid_value \"$1\"); [ -n \"$_p\" ] && kill -0 \"$_p\" 2>/dev/null"

    def run_wait(self, monitor_seconds: float, fail_on: str = "") -> tuple[int, float]:
        script = (self.stubs(self.runner(fail_on), self.KILL0)
                  + function(V142, "_wcc_pid_running") + function(V142, "_wcc_fast_cleaned")
                  + function(V142, "wait_child_cleanup") + "wait_child_cleanup child\n")
        monitor, ended = reaped_sleeper(monitor_seconds)
        self.addCleanup(monitor.kill)
        pidfile = self.tasks / "mix-monitor-child.pid"
        pidfile.write_text(f"{monitor.pid}\n")
        # The monitor's supervisor writes its cleanup proof before it exits.
        (self.tasks / "mix-monitor-child.pid.cleanup.json").write_text("{}\n")
        result = subprocess.run(["sh", "-c", script], timeout=60)
        return result.returncode, time.monotonic() - ended["at"]

    def test_tail_after_monitor_exit_skips_redundant_identity_probes(self):
        code, tail = self.run_wait(1.5)
        self.assertEqual(0, code)
        self.assertLess(tail, 0.8, tail)
        calls = self.calls.read_text().splitlines()
        self.assertEqual(["cleaned", "cleaned"], [call.split()[0] for call in calls])
        self.assertIn("mix_worker.pid child", calls[0])
        self.assertIn("mix-monitor-child.pid child.monitor", calls[1])
        # Old loop: 2 probes at the first tick + 2 after the exit. Now only the
        # first-tick PID-reuse guard runs, and it checks the monitor first.
        self.assertEqual(1, self.probe_count())
        self.assertIn("mix-monitor-child.pid", self.probes.read_text())

    def test_failed_proof_still_reports_unconfirmed_cleanup(self):
        code, _ = self.run_wait(0.5, fail_on="mix-monitor")
        self.assertEqual(125, code)  # same as before: never success without the proof

    def test_waits_for_monitor_with_one_guard_probe_per_two_seconds(self):
        code, _ = self.run_wait(4.5)
        self.assertEqual(0, code)
        # ticks 0, 10, 20 (0.2 s each) while the monitor runs: monitor only.
        self.assertLessEqual(self.probe_count(), 3)


class CommitMonitorPoll(Harness):
    def run_monitor(self, worker_pid: str, alive: str, finish_after: float | None = None,
                    worker_end: dict | None = None) -> tuple[int, float]:
        task_file = self.root / "mix_task.conf"
        task_file.write_text("task=t1\nstate=success\n")
        worker_pidfile = self.tasks / "mix_worker.pid"
        worker_pidfile.write_text(worker_pid + "\n")
        marker = self.root / "finalized"
        script = (self.stubs(self.runner(), alive)
                  + f"TASK_FILE='{task_file}'\nWORKER_PID='{worker_pidfile}'\nLOG_FILE='{self.root}/log'\n"
                  "read_task_value() { sed -n \"s/^${1}=//p\" \"$TASK_FILE\" 2>/dev/null | head -n1; }\n"
                  "luoshu_wake_lock_acquire() { return 1; }\n"
                  "write_finalize_state() { :; }\nmark_legacy_mix_mode() { :; }\n"
                  f"finalize_next_payload() {{ : > '{marker}'; }}\n"
                  + function(RUNTIME, "_monitor_pid_hint") + function(RUNTIME, "monitor_task")
                  + "monitor_task t1\n")
        process = subprocess.Popen(["sh", "-c", script])
        if finish_after is not None:
            time.sleep(finish_after)
            (self.root / "dead").write_text("")
            gone_at = time.monotonic()
        code = process.wait(timeout=60)
        finished = time.monotonic()
        self.assertTrue(marker.exists())
        if worker_end is not None:
            gone_at = worker_end["at"]
        return code, finished - gone_at

    def test_engine_exit_is_committed_within_a_tick_with_few_identity_probes(self):
        worker, ended = reaped_sleeper(5.5)
        self.addCleanup(worker.kill)
        alive = "    _p=$(luoshu_pid_value \"$1\"); [ -n \"$_p\" ] && kill -0 \"$_p\" 2>/dev/null"
        code, latency = self.run_monitor(str(worker.pid), alive, worker_end=ended)
        self.assertEqual(0, code)
        self.assertLess(latency, 0.7, latency)  # was up to 1 s of sleep before the probe
        # Old loop: one Python identity probe every second (~6 here).
        # Now: first tick, the 5 s PID-reuse guard, and the confirming probe.
        self.assertLessEqual(self.probe_count(), 3)
        self.assertEqual(["cleaned"], [line.split()[0] for line in self.calls.read_text().splitlines()])

    def test_contradicted_hint_falls_back_to_one_probe_per_second(self):
        # No usable pid in the record: the hint always says gone, the full
        # probe says alive. Never spin the Python probe at 5 Hz.
        alive = f"    [ ! -e '{self.root}/dead' ]"
        code, _ = self.run_monitor("not-a-pid", alive, finish_after=3.0)
        self.assertEqual(0, code)
        self.assertLessEqual(self.probe_count(), 6)

    def test_budget_is_still_awake_seconds(self):
        body = function(RUNTIME, "monitor_task")
        self.assertIn('while [ $((_ticks / 5)) -lt "$_monitor_limit" ]', body)
        self.assertNotIn("date +%s", body.split("write_finalize_state running")[0])


LOG = """\
[MIX-PHASE] schema=1 request=r1 task=axes-1 component=prepare phase=prepare unit=cjk event=begin uptimeSeconds=99.39
[MIX-PHASE] schema=1 request=r1 task=axes-1 component=prepare phase=prepare unit=cjk event=end uptimeSeconds=100.22 elapsedMs=830 result=ok
[MIX-PHASE] schema=1 request=r1 task=mix-1.apply component=fixed-apply phase=local_commit unit=fixed event=begin uptimeSeconds=119.83
[MIX-PHASE] schema=1 request=r1 task=mix-1.apply component=fixed-apply phase=local_commit unit=fixed event=end uptimeSeconds=120.26 elapsedMs=430 result=ok
[MIX-PHASE] schema=1 request=r1 task=mix-1.monitor component=finalize phase=finalize_lock unit=fixed event=begin uptimeSeconds=121.85
[MIX-PHASE] schema=1 request=r1 task=axes-1 component=worker phase=wait_child_cleanup unit=fixed event=begin uptimeSeconds=122.03
[MIX-PHASE] schema=1 request=r1 task=mix-1.monitor component=finalize phase=finalize_lock unit=fixed event=end uptimeSeconds=122.07 elapsedMs=220 result=ok
[MIX-PHASE] schema=1 request=r1 task=mix-1.monitor component=finalize phase=complete_hyperos unit=fixed event=begin uptimeSeconds=122.12
[MIX-PHASE] schema=1 request=r1 task=mix-1.monitor component=finalize phase=complete_hyperos unit=fixed event=end uptimeSeconds=139.07 elapsedMs=16950 result=ok
[MIX-PHASE] schema=1 request=r1 task=mix-1.monitor component=finalize phase=live_mount unit=fixed event=begin uptimeSeconds=140.29
[STAGE-STEP] component=live step=generation_prepare elapsedMs=25100 status=ok
[STAGE-STEP] component=live step=self_mount elapsedMs=2900 status=ok
[MIX-PHASE] schema=1 request=r1 task=mix-1.monitor component=finalize phase=live_mount unit=fixed event=end uptimeSeconds=168.43 elapsedMs=28140 result=ok
[MIX-PHASE] schema=1 request=r1 task=mix-1.monitor component=finalize phase=finalize_release unit=fixed event=begin uptimeSeconds=168.45
[MIX-PHASE] schema=1 request=r1 task=mix-1.monitor component=finalize phase=finalize_release unit=fixed event=end uptimeSeconds=168.60 elapsedMs=150 result=ok
[MIX-PHASE] schema=1 request=r1 task=axes-1 component=worker phase=wait_child_cleanup unit=fixed event=end uptimeSeconds=169.51 elapsedMs=47480 result=ok
[MIX-PHASE] schema=1 request=r1 task=axes-1 component=worker phase=worker_finalize unit=fixed event=begin uptimeSeconds=169.51
[MIX-PHASE] schema=1 request=r1 task=axes-1 component=worker phase=worker_finalize unit=fixed event=end uptimeSeconds=170.04 elapsedMs=530 result=ok
"""


class DiagnosticWallClock(unittest.TestCase):
    def test_wait_is_split_into_overlapped_finalize_and_own_tail(self):
        with tempfile.TemporaryDirectory() as temp:
            module = Path(temp)
            (module / "logs").mkdir()
            (module / "logs/fontswitch.log").write_text(LOG)
            last = locator.last_apply_log(module, str)
        # Legacy sum kept for old readers; it double counts the wait.
        self.assertEqual(830 + 430 + 220 + 16950 + 28140 + 150 + 47480 + 530, last["totalPhaseMs"])
        self.assertEqual(70650, last["wallMs"])  # 99.39 -> 170.04
        self.assertEqual(1590, last["commitHandoffMs"])  # local_commit end -> finalize_lock begin
        wait = last["waitChildCleanup"]
        self.assertEqual(47480, wait["elapsedMs"])
        # 122.03-122.07, 122.12-139.07, 140.29-168.43, 168.45-168.60 overlap the wait.
        self.assertEqual(40 + 16950 + 28140 + 150, wait["overlapFinalizeMs"])
        self.assertEqual(47480 - (40 + 16950 + 28140 + 150), wait["ownMs"])
        self.assertEqual(910, wait["tailAfterFinalizeMs"])
        live = [row for row in last["stageSteps"] if row["component"] == "live"]
        self.assertEqual([("generation_prepare", 25100), ("self_mount", 2900)],
                         [(row["step"], row["elapsedMs"]) for row in live])

    def test_safe_switch_only_apply_has_no_wall_fields(self):
        self.assertEqual({}, locator.mix_wall_clock(["[SAFE-TIMING] task=a event=begin phase=x uptime=1.0"], None))


class LiveMountSteps(unittest.TestCase):
    def test_step_lines_go_to_stderr_in_the_parsed_format(self):
        source = LIVE.read_text(encoding="utf-8")
        helpers = "\n".join(line for line in source.splitlines()
                            if line.startswith("_live_uptime_ms()"))
        helpers += "\n" + function(LIVE, "_live_step")
        result = subprocess.run(["sh", "-c", helpers + "\n_b=$(_live_uptime_ms)\nsleep 0.3\n"
                                 "_live_step generation_prepare \"$_b\" ok\n"],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual("", result.stdout)  # stdout stays the result JSON only
        steps = locator.stage_steps(result.stderr.splitlines())
        self.assertEqual(1, len(steps))
        self.assertEqual(("live", "generation_prepare", "ok"),
                         (steps[0]["component"], steps[0]["step"], steps[0]["status"]))
        self.assertGreaterEqual(steps[0]["elapsedMs"], 250)
        # Both parts of live_mount are measured, on success and on failure.
        self.assertEqual(2, source.count("_live_step generation_prepare"))
        self.assertEqual(2, source.count("_live_step self_mount"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
