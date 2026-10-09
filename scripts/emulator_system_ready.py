#!/usr/bin/env python3
"""Read-only emulator system readiness inside the original 600s boot budget.

This is neither target-App startup nor the 20s helper/30s Launcher preparation.
Never launches an Activity, dismisses keyguard, changes settings, or warms the App.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import re
import subprocess
import time

BOOT_BUDGET_SECONDS = 600


def resources() -> dict:
    result = {"cpu_count": os.cpu_count()}
    try:
        result["cpu_affinity"] = sorted(os.sched_getaffinity(0))
    except (AttributeError, OSError) as error:
        result["cpu_affinity_error"] = str(error)
    for name in ("/proc/meminfo", "/proc/pressure/cpu", "/proc/pressure/memory", "/proc/pressure/io",
                 "/sys/fs/cgroup/cpu.max", "/sys/fs/cgroup/memory.max"):
        try:
            result[name] = Path(name).read_text()
        except OSError as error:
            result[name] = {"unavailable": str(error)}
    return result


def begin(output: Path, clock=time.monotonic) -> None:
    output.mkdir(parents=True, exist_ok=True)
    now = clock()
    state = {"scope": "emulator-system-boot-only", "started_monotonic_seconds": now,
             "deadline_monotonic_seconds": now + BOOT_BUDGET_SECONDS,
             "budget_seconds": BOOT_BUDGET_SECONDS, "started_unix_seconds": time.time(),
             "resources_before_boot": resources(), "target_app_launch_requested": False}
    # A second begin must not silently reset an existing deadline.
    with (output / "boot-deadline.json").open("x") as file:
        json.dump(state, file, indent=2)


def block(text: str, heading: str) -> str:
    matches = list(re.finditer(rf"^([ \t]*){re.escape(heading)}[ \t]*$", text, re.M))
    if len(matches) != 1:
        raise ValueError(f"missing-or-ambiguous-{heading}")
    match = matches[0]
    indent = len(match.group(1))
    result = []
    for line in text[match.end():].lstrip("\r\n").splitlines():
        if re.fullmatch(r"-+", line.strip()):
            continue  # SystemUI DumpManager separator is at the heading indentation.
        if line.strip() and len(line) - len(line.lstrip()) <= indent:
            break
        result.append(line)
    return "\n".join(result)


def field(text: str, name: str) -> str:
    values = re.findall(rf"(?<![\w]){re.escape(name)}=([^\s]+)", text)
    if len(values) != 1:
        raise ValueError(f"missing-or-ambiguous-{name}")
    return values[0]


def normalized(component: str) -> str:
    if not re.fullmatch(r"[\w.$]+/[\w.$]+", component):
        raise ValueError("invalid-component")
    package, activity = component.split("/")
    return package + "/" + (package + activity if activity.startswith(".") else activity)


def identity(line: str) -> tuple[int, str]:
    matches = re.findall(r"\bu(\d+)\s+([\w.$]+/[\w.$]+)(?=[\s}])", line)
    if len(matches) != 1:
        raise ValueError("missing-or-ambiguous-window-identity")
    user, component = matches[0]
    return int(user), normalized(component)


def current_user(value: str) -> int:
    if not re.fullmatch(r"\d+", value.strip()):
        raise ValueError("invalid-current-user")
    return int(value.strip())


def focus(window: str) -> tuple[int, str]:
    lines = re.findall(r"^\s*mCurrentFocus=(.*)$", window, re.M)
    if len(lines) != 1 or not re.fullmatch(r"Window\{[^{}]+\}", lines[0].strip()):
        raise ValueError("missing-or-ambiguous-window-focus")
    return identity(lines[0])


def evaluate(values: dict[str, str]) -> dict:
    result = {"ready": False, "reasons": []}
    try:
        if values["boot"].strip() != "1":
            raise ValueError("boot-property-not-complete")
        user = current_user(values["user"])
        if current_user(values["user_after"]) != user:
            raise ValueError("user-changed-during-sample")
        homes = re.findall(r"^([\w.$]+/[\w.$]+)$", values["home"], re.M)
        if len(homes) != 1:
            raise ValueError("missing-or-ambiguous-resolved-home")
        home = normalized(homes[0])
        expected = (user, home)
        for key in ("window", "window_after"):
            window = values[key]
            if focus(window) != expected:
                raise ValueError("home-focus-user-mismatch")
            delegate = block(window, "KeyguardServiceDelegate")
            monitor = block(delegate, "KeyguardStateMonitor")
            if current_user(field(monitor, "mCurrentUserId")) != user:
                raise ValueError("keyguard-monitor-user-mismatch")
            # Delegate.currentUser is a replay cache and can remain USER_NULL until a user switch.
            # Do not use it to invent an unlocked user; verify the live monitor + am instead.
            cached_user = field(delegate, "currentUser")
            if cached_user != "-10000" and current_user(cached_user) != user:
                raise ValueError("keyguard-delegate-user-mismatch")
            result["delegate_cached_user"] = cached_user
            for name, expected_value in (("systemIsReady", "true"), ("bootCompleted", "true"),
                    ("showing", "false"), ("inputRestricted", "false"), ("occluded", "false"),
                    ("screenState", "SCREEN_STATE_ON"), ("interactiveState", "INTERACTIVE_STATE_AWAKE")):
                if field(delegate, name) != expected_value:
                    raise ValueError("delegate-not-ready-" + name)
            for name in ("mIsShowing", "mInputRestricted"):
                if field(monitor, name) != "false":
                    raise ValueError("monitor-not-ready-" + name)
            for name in ("mAwake", "mScreenOnFully", "mKeyguardDrawComplete", "mWindowManagerDrawComplete"):
                if field(window, name) != "true":
                    raise ValueError("window-not-ready-" + name)
            if field(window, "isKeyguardShowing") != "false":
                raise ValueError("display-keyguard-showing")
        systemui = values["systemui"]
        headings = re.findall(r"^\s*((?:com\.android\.systemui\.keyguard\.)?KeyguardViewMediator:)\s*$", systemui, re.M)
        if len(headings) != 1:
            raise ValueError("missing-or-ambiguous-SystemUI-mediator")
        mediator = block(systemui, headings[0])
        for name, expected_value in (("mSystemReady", "true"), ("mBootCompleted", "true"),
                                     ("mShowing", "false"), ("mInputRestricted", "false"),
                                     ("mOccluded", "false"), ("mDeviceInteractive", "true")):
            parsed = [value.strip() for value in re.findall(rf"^[ \t]*{name}:[ \t]*([^\r\n]*)$", mediator, re.M)]
            if parsed != [expected_value]:
                raise ValueError("SystemUI-not-ready-" + name)
        resumed = re.findall(r"^[ \t]*(?:Resumed|ResumedActivity|mResumedActivity|topResumedActivity)[ \t]*[:=][ \t]*([^\r\n]*)$", values["activities"], re.M)
        if not resumed or any(not re.fullmatch(r"ActivityRecord\{[^{}]+\}", line.strip()) or
                              identity(line) != expected for line in resumed):
            raise ValueError("home-not-uniquely-resumed")
        if values["target_pid"].strip():
            raise ValueError("target-app-already-running")
        result.update(ready=True, identity=[user, home])
    except (ValueError, KeyError) as error:
        result["reasons"].append(str(error))
    return result


def wait(output: Path, serial: str, *, clock=time.monotonic, pause=time.sleep, runner=subprocess.run) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    report = {"scope": "emulator-system-boot-only; not App startup or Launcher sample acceptance",
              "passed": False, "target_app_launch_requested": False, "samples_reusable_for_acceptance": False,
              "observations": [], "commands": []}
    try:
        state = json.loads((output / "boot-deadline.json").read_text())
        started, deadline = float(state["started_monotonic_seconds"]), float(state["deadline_monotonic_seconds"])
        if state["budget_seconds"] != BOOT_BUDGET_SECONDS or not all(math.isfinite(value) for value in (started, deadline)) or \
                not math.isclose(deadline - started, BOOT_BUDGET_SECONDS, rel_tol=0, abs_tol=1e-6) or clock() < started:
            raise ValueError("invalid-original-boot-deadline")
        report.update(started_monotonic_seconds=started, deadline_monotonic_seconds=deadline)
        def remaining() -> float:
            available = deadline - clock()
            if available <= 0:
                raise TimeoutError("Original 600s emulator boot/system-ready budget exhausted")
            return available
        def read(name: str, args: list[str], *, absent_ok: bool = False) -> str:
            timeout = min(5.0, remaining())
            index = len(report["commands"]) + 1
            record = {"name": name, "args": args, "started_monotonic_seconds": clock(), "timeout_seconds": timeout}
            stdout = stderr = b""
            try:
                completed = runner(["adb", "-s", serial, "shell", *args], stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, timeout=timeout, check=False)
                stdout, stderr = completed.stdout, completed.stderr
                record["returncode"] = completed.returncode
                if completed.returncode != 0 and not (absent_ok and completed.returncode == 1 and not stdout.strip() and not stderr.strip()):
                    raise RuntimeError(f"{name}: adb exit {completed.returncode}")
                remaining()
                return stdout.decode("utf-8", "strict")
            except subprocess.TimeoutExpired as error:
                stdout, stderr = error.stdout or b"", error.stderr or b""
                record["error"] = "command-timeout"
                raise RuntimeError(f"{name}: bounded adb timeout") from error
            finally:
                prefix = f"command-{index:04d}-{name}"
                (output / (prefix + ".stdout")).write_bytes(stdout)
                (output / (prefix + ".stderr")).write_bytes(stderr)
                record.update(finished_monotonic_seconds=clock(), stdout=prefix + ".stdout", stderr=prefix + ".stderr")
                report["commands"].append(record)
        stable, previous = 0, None
        while True:
            remaining()
            observation = {"started_monotonic_seconds": clock()}
            try:
                values = {"boot": read("boot", ["getprop", "sys.boot_completed"]),
                          "user": read("user", ["am", "get-current-user"])}
                user = current_user(values["user"])
                values["home"] = read("home", ["cmd", "package", "resolve-activity", "--brief", "--user", str(user), "-a", "android.intent.action.MAIN", "-c", "android.intent.category.HOME"])
                values["window"] = read("window", ["dumpsys", "window"])
                values["systemui"] = read("systemui", ["dumpsys", "activity", "service", "com.android.systemui/.SystemUIService", "KeyguardViewMediator"])
                values["activities"] = read("activities", ["dumpsys", "activity", "activities"])
                values["user_after"] = read("user-after", ["am", "get-current-user"])
                values["window_after"] = read("window-after", ["dumpsys", "window"])
                values["target_pid"] = read("target-pid", ["pidof", "io.github.xgl34222220.luoshu.debug"], absent_ok=True)
                observation.update(evaluate(values))
            except (RuntimeError, ValueError, UnicodeError) as error:
                observation.update(ready=False, reasons=[str(error)])
            remaining()
            signature = observation.get("identity") if observation["ready"] else None
            stable = stable + 1 if signature is not None and signature == previous else int(signature is not None)
            previous = signature
            observation.update(stable_observations=stable, finished_monotonic_seconds=clock())
            report["observations"].append(observation)
            if stable >= 2:
                report["passed"] = True
                return report
            pause(min(2.0, remaining()))
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
        return report
    finally:
        report["finished_monotonic_seconds"] = clock()
        report["resources_after_gate"] = resources()
        (output / "system-ready.json").write_text(json.dumps(report, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("begin", "wait"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--serial", default="emulator-5554")
    args = parser.parse_args()
    if args.action == "begin":
        begin(args.output)
        return 0
    report = wait(args.output, args.serial)
    print(json.dumps({key: report.get(key) for key in ("passed", "error", "started_monotonic_seconds", "finished_monotonic_seconds")}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
