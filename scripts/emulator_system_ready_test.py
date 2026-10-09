#!/usr/bin/env python3
"""Parser negatives and fake-clock budget tests; no emulator or target App launch."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import emulator_system_ready as gate

HOME = "com.google.android.apps.nexuslauncher/com.google.android.apps.nexuslauncher.NexusLauncherActivity"
WINDOW = '''WINDOW MANAGER POLICY STATE
  KeyguardServiceDelegate
    showing=false
    inputRestricted=false
    occluded=false
    systemIsReady=true
    currentUser=-10000
    bootCompleted=true
    screenState=SCREEN_STATE_ON
    interactiveState=INTERACTIVE_STATE_AWAKE
    KeyguardStateMonitor
      mIsShowing=false
      mInputRestricted=false
      mCurrentUserId=0
  EndDelegate
  mCurrentFocus=Window{e32cbf6 u0 com.google.android.apps.nexuslauncher/com.google.android.apps.nexuslauncher.NexusLauncherActivity}
  mAwake=true mScreenOnFully=true
  mKeyguardDrawComplete=true mWindowManagerDrawComplete=true
  isKeyguardShowing=false
'''
SYSTEMUI = '''SERVICE com.android.systemui/.SystemUIService
  com.android.systemui.keyguard.KeyguardViewMediator:
  ----------------------------------------------------------------------------
    mSystemReady: true
    mBootCompleted: true
    mShowing: false
    mInputRestricted: false
    mOccluded: false
    mDeviceInteractive: true
  NextDumpable:
    mSystemReady: false
'''
ACTIVITIES = '''Resumed activities in task display areas (from top to bottom):
    Resumed: ActivityRecord{146045965 u0 com.google.android.apps.nexuslauncher/.NexusLauncherActivity t6}
  ResumedActivity: ActivityRecord{146045965 u0 com.google.android.apps.nexuslauncher/.NexusLauncherActivity t6}
'''

def values():
    return {"boot": "1\n", "user": "0\n", "user_after": "0\n",
            "home": "priority=0\ncom.google.android.apps.nexuslauncher/.NexusLauncherActivity\n",
            "window": WINDOW, "window_after": WINDOW, "activities": ACTIVITIES,
            "systemui": SYSTEMUI, "target_pid": ""}


class ParseTest(unittest.TestCase):
    def test_user_zero_and_delegate_replay_sentinel_use_live_monitor(self):
        result = gate.evaluate(values())
        self.assertTrue(result["ready"], result)
        self.assertEqual(result["identity"], [0, HOME])
        self.assertEqual(result["delegate_cached_user"], "-10000")

    def test_boot_completed_alone_is_not_readiness(self):
        self.assertFalse(gate.evaluate({"boot": "1"})["ready"])
        sample = values(); sample["boot"] = "0"
        self.assertFalse(gate.evaluate(sample)["ready"])

    def test_real_failure_setup_resumed_despite_launcher_focus(self):
        # From e6ca run37867487521 attempt2 artifact11589423858 activity.txt.
        sample = values()
        sample["activities"] = '''  Resumed activities in task display areas (from top to bottom):
    Resumed: ActivityRecord{201025347 u0 com.google.android.gms/.setupservices.CoverSheetWelcomeActivity t7}
  ResumedActivity: ActivityRecord{201025347 u0 com.google.android.gms/.setupservices.CoverSheetWelcomeActivity t7}
'''
        result = gate.evaluate(sample)
        self.assertEqual(result["reasons"], ["home-not-uniquely-resumed"])

    def test_every_required_window_field_missing_or_ambiguous_fails(self):
        for field in ("systemIsReady", "bootCompleted", "showing", "inputRestricted", "occluded",
                      "screenState", "interactiveState", "mIsShowing", "mCurrentUserId",
                      "mAwake", "mScreenOnFully", "mKeyguardDrawComplete", "mWindowManagerDrawComplete",
                      "isKeyguardShowing"):
            for ambiguous in (False, True):
                sample = values()
                sample["window"] = sample["window"].replace(field + "=", field + "_missing=", 1)
                if ambiguous:
                    sample["window"] = WINDOW.replace(field + "=", field + "=true " + field + "=", 1)
                self.assertFalse(gate.evaluate(sample)["ready"], (field, ambiguous))

    def test_window_ready_but_systemui_message_not_processed_fails(self):
        for key in ("mSystemReady", "mBootCompleted", "mDeviceInteractive"):
            sample = values(); sample["systemui"] = SYSTEMUI.replace(key + ": true", key + ": false", 1)
            self.assertFalse(gate.evaluate(sample)["ready"], key)
        sample = values(); sample["systemui"] = "Can't find service"
        self.assertFalse(gate.evaluate(sample)["ready"])

    def test_user_switch_and_stale_final_focus_fail(self):
        for key, value in (("user", "-10000"), ("user_after", "10"),
                           ("window_after", WINDOW.replace("u0", "u10")),
                           ("window", WINDOW.replace("mCurrentUserId=0", "mCurrentUserId=10")),
                           ("window", WINDOW.replace("currentUser=-10000", "currentUser=10"))):
            sample = values(); sample[key] = value
            self.assertFalse(gate.evaluate(sample)["ready"], key)

    def test_lock_conflicts_sleep_undrawn_and_target_pid_fail(self):
        for old, new in (("showing=false", "showing=true"), ("occluded=false", "occluded=true"),
                         ("mScreenOnFully=true", "mScreenOnFully=false"),
                         ("mWindowManagerDrawComplete=true", "mWindowManagerDrawComplete=false"),
                         ("mIsShowing=false", "mIsShowing=true"),
                         ("isKeyguardShowing=false", "isKeyguardShowing=true")):
            sample = values(); sample["window"] = WINDOW.replace(old, new)
            self.assertFalse(gate.evaluate(sample)["ready"], old)
        sample = values(); sample["target_pid"] = "1234"
        self.assertFalse(gate.evaluate(sample)["ready"])

    def test_null_or_malformed_resumed_alias_cannot_hide_beside_valid_home(self):
        for bad in ("ResumedActivity: null", "topResumedActivity=null", "mResumedActivity: malformed"):
            sample = values(); sample["activities"] += "  " + bad + "\n"
            self.assertFalse(gate.evaluate(sample)["ready"], bad)

    def test_malformed_duplicate_systemui_field_cannot_hide_beside_valid_value(self):
        sample = values(); sample["systemui"] = SYSTEMUI.replace("    mSystemReady: true", "    mSystemReady: true\n    mSystemReady: malformed")
        self.assertFalse(gate.evaluate(sample)["ready"])

    def test_resumed_aliases_may_agree_but_mixed_users_do_not(self):
        sample = values(); sample["activities"] += '  topResumedActivity=ActivityRecord{abc u10 x.y/.Main t7}\n'
        self.assertFalse(gate.evaluate(sample)["ready"])
        sample = values(); sample["home"] += HOME + "\n"
        self.assertFalse(gate.evaluate(sample)["ready"])


class Clock:
    def __init__(self, now=0): self.now = now
    def __call__(self): return self.now
    def sleep(self, duration): self.now += duration


class BudgetTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.output = Path(self.temp.name)
        self.clock = Clock(); self.calls = []; self.batch = -1
        self.resource_patch = patch.object(gate, "resources", return_value={}); self.resource_patch.start()
        gate.begin(self.output, clock=self.clock)
    def tearDown(self):
        self.resource_patch.stop(); self.temp.cleanup()
    def runner(self, command, **kwargs):
        self.calls.append((command, kwargs["timeout"]))
        self.clock.now += .1
        args = command[4:]
        if args[0] == "getprop": self.batch += 1
        data = self.sample(self.batch)
        if args[:2] == ["getprop", "sys.boot_completed"]: value = data["boot"]
        elif args[:2] == ["am", "get-current-user"]: value = data["user"]
        elif args[:3] == ["cmd", "package", "resolve-activity"]: value = data["home"]
        elif args[:2] == ["dumpsys", "window"]: value = data["window"]
        elif args[:3] == ["dumpsys", "activity", "activities"]: value = data["activities"]
        elif args[:3] == ["dumpsys", "activity", "service"]: value = data["systemui"]
        elif args[0] == "pidof": return subprocess.CompletedProcess(command, 1, b"", b"")
        else: raise AssertionError(command)
        return subprocess.CompletedProcess(command, 0, value.encode(), b"")
    def sample(self, batch): return values()
    def run_gate(self, runner=None):
        return gate.wait(self.output, "emulator-5554", clock=self.clock, pause=self.clock.sleep,
                         runner=runner or self.runner)
    def test_two_complete_consistent_observations_required(self):
        report = self.run_gate()
        self.assertTrue(report["passed"]); self.assertEqual(len(report["observations"]), 2)
        self.assertEqual([x["stable_observations"] for x in report["observations"]], [1, 2])
        self.assertFalse(report["target_app_launch_requested"])
        self.assertFalse(report["samples_reusable_for_acceptance"])
        self.assertTrue(all(x[0][3] == "shell" for x in self.calls))
        self.assertNotIn("start", " ".join(" ".join(x[0]) for x in self.calls))
    def test_bad_observation_resets_stability(self):
        def sample(batch):
            data = values()
            if batch == 1: data["boot"] = "0"
            return data
        self.sample = sample
        report = self.run_gate()
        self.assertEqual([x["stable_observations"] for x in report["observations"]], [1, 0, 1, 2])
    def test_expired_original_clock_never_calls_adb(self):
        self.clock.now = 600
        report = self.run_gate(); self.assertFalse(report["passed"]); self.assertFalse(self.calls)
    def test_remaining_budget_caps_each_command_and_late_success_rejected(self):
        self.clock.now = 599.8
        def late(command, **kwargs):
            self.calls.append((command, kwargs["timeout"]))
            self.clock.now += 1
            return subprocess.CompletedProcess(command, 0, b"1\n", b"")
        report = self.run_gate(late)
        self.assertFalse(report["passed"])
        self.assertAlmostEqual(self.calls[0][1], .2)
        self.assertTrue(list(self.output.glob('*.stdout')))
    def test_timeout_preserves_partial_output_and_cannot_extend_deadline(self):
        self.clock.now = 599
        def timeout(command, **kwargs):
            self.clock.now += kwargs["timeout"]
            raise subprocess.TimeoutExpired(command, kwargs["timeout"], output=b'partial', stderr=b'diagnostic')
        report = self.run_gate(timeout)
        self.assertFalse(report["passed"]); self.assertEqual(self.clock.now, 600)
        self.assertEqual(next(self.output.glob('*.stdout')).read_bytes(), b'partial')
        self.assertEqual(next(self.output.glob('*.stderr')).read_bytes(), b'diagnostic')
    def test_missing_malformed_future_or_reset_clock_fails_closed(self):
        path = self.output/'boot-deadline.json'
        for value in ('bad json', '{}', json.dumps({'budget_seconds': 600, 'started_monotonic_seconds': 1, 'deadline_monotonic_seconds': 601}),
                      json.dumps({'budget_seconds': 601, 'started_monotonic_seconds': 0, 'deadline_monotonic_seconds': 601})):
            path.write_text(value); self.assertFalse(self.run_gate()["passed"])
        path.unlink(); self.assertFalse(self.run_gate()["passed"]); self.assertFalse(self.calls)
    def test_real_monotonic_fraction_does_not_fail_exact_float_subtraction(self):
        (self.output/'boot-deadline.json').unlink()
        self.clock.now = 548.123456789
        gate.begin(self.output, clock=self.clock)
        self.assertTrue(self.run_gate()["passed"])

    def test_begin_cannot_reset_existing_deadline(self):
        with self.assertRaises(FileExistsError): gate.begin(self.output, clock=self.clock)


if __name__ == '__main__': unittest.main()
