#!/usr/bin/env python3
"""Capture real emulator screens and fail on navigation, process, crash or ANR errors.

Requires an already booted emulator and an installable debug APK. This checks the
unrooted App UI, not font replacement on HyperOS/ColorOS. Screenshots are raw adb
screencap output; no mock data, screenshots or crash suppression are injected.
"""

from __future__ import annotations

import argparse
import json
import re
import struct
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path


PAGES = (
    ("home", "首页", "当前字体"),
    ("library", "字体库", "搜索你的字体"),
    ("studio", "组合", "字体组合"),
    ("settings", "设置", "你的洛书"),
)
BOUNDS = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


def labels(node: ET.Element) -> set[str]:
    values = (node.get("text", ""), node.get("content-desc", ""))
    return {line.strip() for value in values for line in value.splitlines() if line.strip()}


def bounds(node: ET.Element) -> tuple[int, int, int, int]:
    match = BOUNDS.fullmatch(node.get("bounds", ""))
    if not match:
        raise ValueError(f"Invalid UI bounds: {node.get('bounds')!r}")
    left, top, right, bottom = map(int, match.groups())
    if right <= left or bottom <= top:
        raise ValueError("UI node has no visible bounds")
    return left, top, right, bottom


def center(node: ET.Element) -> tuple[int, int]:
    left, top, right, bottom = bounds(node)
    return (left + right) // 2, (top + bottom) // 2


def tab_target(root: ET.Element, label: str, package: str) -> ET.Element:
    page_labels = [page[1] for page in PAGES]
    page_label_set = set(page_labels)
    app_nodes = [node for node in root.iter("node") if node.get("package") == package]
    valid_bounds = []
    for node in app_nodes:
        try:
            valid_bounds.append(bounds(node))
        except ValueError:
            continue
    if not valid_bounds:
        raise ValueError("App bounds not found in the hierarchy")
    screen_bottom = max(rect[3] for rect in valid_bounds)
    targets = []
    for group in app_nodes:
        tabs = {}
        for child in group:
            child_labels = {value for node in child.iter("node") if node.get("package") == package for value in labels(node)} & page_label_set
            if len(child_labels) != 1:
                continue
            child_label = child_labels.pop()
            if child_label in tabs:
                tabs = {}
                break
            tabs[child_label] = child
        if set(tabs) != page_label_set:
            continue
        try:
            ordered = [tabs[value] for value in page_labels]
            centers = [center(node) for node in ordered]
            heights = [bounds(node)[3] - bounds(node)[1] for node in ordered]
        except ValueError:
            continue
        if any(node.get("package") != package or node.get("enabled") == "false" for node in ordered):
            continue
        if any(node.get("clickable") != "true" and not (
            node.get("focusable") == "true" and node.get("selected") == "true"
        ) for node in ordered):
            continue
        if any(centers[index][0] >= centers[index + 1][0] for index in range(len(centers) - 1)):
            continue
        if max(y for _, y in centers) - min(y for _, y in centers) > min(heights) / 2:
            continue
        if min(y for _, y in centers) < screen_bottom * 0.65:
            continue
        target = tabs[label]
        targets.append(target)
    if not targets:
        raise ValueError(f"Bottom navigation tab {label!r} not found in the App hierarchy")
    # AndroidX deliberately exposes an already-selected Role.Tab as non-clickable.
    # Accept its focusable parent only inside the complete, horizontal four-tab
    # group. The subsequent real tap must still select the requested page and body.
    return max(targets, key=lambda node: (center(node)[1], node.get("clickable") == "true"))


def page_ready(root: ET.Element, label: str, marker: str, package: str) -> bool:
    try:
        target = tab_target(root, label, package)
    except ValueError:
        return False
    selected = any(node.get("selected") == "true" for node in target.iter())
    content = any(marker in labels(node) and node.get("package") == package for node in root.iter("node"))
    return selected and content


def crash_reason(log: str, package: str) -> str | None:
    escaped = re.escape(package)
    if re.search(rf"\bANR in {escaped}(?:\s|$|:)", log):
        return "App ANR recorded by ActivityManager"
    # AndroidRuntime emits the process name on the lines following FATAL EXCEPTION.
    for match in re.finditer(r"FATAL EXCEPTION:", log):
        block = log[match.start():match.start() + 5_000]
        if re.search(rf"\bProcess: {escaped}(?:,|:)", block):
            return "App Java/Kotlin FATAL EXCEPTION recorded by AndroidRuntime"
    if re.search(rf">>> {escaped}(?::[^ ]+)? <<<", log):
        return "App native crash tombstone recorded by debuggerd"
    return None


class SmokeRun:
    def __init__(self, apk: Path, output: Path, package: str, serial: str | None):
        self.apk = apk
        self.output = output
        self.package = package
        self.adb_command = ["adb"] + (["-s", serial] if serial else [])
        self.output.mkdir(parents=True, exist_ok=True)
        self.results: list[dict[str, object]] = []
        self.started_at = time.monotonic()

    def adb(self, *arguments: str, timeout: float = 20, check: bool = True) -> subprocess.CompletedProcess[bytes]:
        try:
            result = subprocess.run(self.adb_command + list(arguments), capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(f"adb timed out after {timeout}s: {' '.join(arguments)}") from error
        if check and result.returncode:
            detail = (result.stdout + result.stderr).decode("utf-8", "replace")[-3_000:]
            raise RuntimeError(f"adb {' '.join(arguments)} failed ({result.returncode}): {detail}")
        return result

    def text(self, *arguments: str, **kwargs: object) -> str:
        return self.adb(*arguments, **kwargs).stdout.decode("utf-8", "replace")

    def hierarchy(self) -> ET.Element:
        remote = "/sdcard/luoshu-ui-smoke.xml"
        self.adb("shell", "rm", "-f", remote)
        self.adb("shell", "uiautomator", "dump", remote, timeout=15)
        xml = self.text("shell", "cat", remote)
        (self.output / "latest-hierarchy.xml").write_text(xml, encoding="utf-8")
        return ET.fromstring(xml)

    def logcat(self, filename: str = "logcat.txt") -> str:
        log = self.text("logcat", "-b", "main", "-b", "system", "-b", "crash", "-d", "-v", "threadtime")
        (self.output / filename).write_text(log, encoding="utf-8")
        return log

    def assert_running(self) -> None:
        failure = crash_reason(self.logcat(), self.package)
        if failure:
            raise RuntimeError(failure)
        if not self.text("shell", "pidof", self.package, check=False).strip():
            raise RuntimeError("App process is no longer running")

    def wait_page(self, label: str, marker: str, timeout: float = 45) -> ET.Element:
        deadline = time.monotonic() + timeout
        last_error = "No hierarchy received"
        while time.monotonic() < deadline:
            self.assert_running()
            try:
                root = self.hierarchy()
                if page_ready(root, label, marker, self.package):
                    return root
                last_error = f"Tab {label!r} is not selected or page text {marker!r} is absent"
            except (RuntimeError, ET.ParseError) as error:
                last_error = str(error)
            time.sleep(0.4)
        raise RuntimeError(f"UI page did not become ready within {timeout}s: {last_error}")

    def capture(self, name: str, root: ET.Element) -> None:
        self.assert_running()
        png = self.adb("exec-out", "screencap", "-p").stdout
        if len(png) < 24 or not png.startswith(b"\x89PNG\r\n\x1a\n"):
            raise RuntimeError("adb screencap did not return a PNG image")
        width, height = struct.unpack(">II", png[16:24])
        if width < 300 or height < 300:
            raise RuntimeError(f"Unexpected screenshot size: {width}x{height}")
        (self.output / f"{name}.png").write_bytes(png)
        ET.ElementTree(root).write(self.output / f"{name}.xml", encoding="utf-8", xml_declaration=True)
        self.results.append({"screen": name, "width": width, "height": height, "passed": True})
        print(f"Captured {name}: {width}x{height}", flush=True)

    def run(self) -> None:
        self.adb("wait-for-device", timeout=60)
        self.adb("install", "-r", "-g", str(self.apk), timeout=120)
        self.adb("shell", "pm", "clear", self.package)
        # Clearing App data also revokes the grant made by install -g. Grant this
        # permission after the reset so the first-run dialog cannot cover the UI.
        self.adb("shell", "pm", "grant", self.package, "android.permission.POST_NOTIFICATIONS")
        self.adb("logcat", "-c")
        self.adb("shell", "input", "keyevent", "KEYCODE_WAKEUP")
        self.adb("shell", "wm", "dismiss-keyguard")
        self.adb("shell", "cmd", "uimode", "night", "no")
        launch = self.text("shell", "am", "start", "-W", "-n", f"{self.package}/io.github.xgl34222220.luoshu.MainActivity", timeout=45)
        (self.output / "launch.txt").write_text(launch, encoding="utf-8")
        if "Status: ok" not in launch or "Error:" in launch:
            raise RuntimeError(f"MainActivity launch failed: {launch}")
        self.wait_page("首页", "当前字体")
        for theme in ("light", "dark"):
            if theme == "dark":
                self.adb("shell", "cmd", "uimode", "night", "yes")
                # Let the actual configuration change and Activity recreation finish.
                time.sleep(1.5)
            mode = self.text("shell", "cmd", "uimode", "night")
            (self.output / f"{theme}-system-mode.txt").write_text(mode, encoding="utf-8")
            expected_mode = "yes" if theme == "dark" else "no"
            if not re.search(rf"Night mode:\s*{expected_mode}\b", mode, re.IGNORECASE):
                raise RuntimeError(f"System night mode was not applied: {mode.strip()}")
            for name, label, marker in PAGES:
                root = self.hierarchy()
                target = tab_target(root, label, self.package)
                x, y = center(target)
                self.adb("shell", "input", "tap", str(x), str(y))
                root = self.wait_page(label, marker)
                # Keep the production animations enabled; capture once navigation settles.
                time.sleep(0.7)
                self.capture(f"{theme}-{name}", root)
        # Exercise STOPPED -> STARTED without stopping the process or masking crashes.
        self.adb("shell", "input", "keyevent", "KEYCODE_HOME")
        time.sleep(1)
        self.adb("shell", "am", "start", "-W", "-n", f"{self.package}/io.github.xgl34222220.luoshu.MainActivity", timeout=45)
        root = self.wait_page("设置", "你的洛书")
        self.capture("dark-settings-resumed", root)
        self.assert_running()

    def diagnostics(self) -> None:
        for filename, arguments in (
            ("logcat.txt", ("logcat", "-b", "all", "-d", "-v", "threadtime")),
            ("activity.txt", ("shell", "dumpsys", "activity", "activities")),
            ("memory.txt", ("shell", "dumpsys", "meminfo", self.package)),
            ("uimode.txt", ("shell", "dumpsys", "uimode")),
            ("device.txt", ("shell", "getprop")),
        ):
            try:
                (self.output / filename).write_bytes(self.adb(*arguments, check=False).stdout)
            except RuntimeError as error:
                print(f"Could not collect {filename}: {error}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apk", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--package", default="io.github.xgl34222220.luoshu.debug")
    parser.add_argument("--serial")
    args = parser.parse_args()
    if not args.apk.is_file():
        parser.error(f"APK does not exist: {args.apk}")
    if not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+", args.package):
        parser.error("Invalid Android package name")
    run = SmokeRun(args.apk.resolve(), args.output.resolve(), args.package, args.serial)
    error = None
    try:
        run.run()
    except Exception as failure:
        error = f"{type(failure).__name__}: {failure}"
        print(error, file=sys.stderr, flush=True)
        try:
            # Preserve the real failure screen even if hierarchy collection itself failed.
            png = run.adb("exec-out", "screencap", "-p", check=False).stdout
            if png.startswith(b"\x89PNG\r\n\x1a\n"):
                (run.output / "failure.png").write_bytes(png)
        except RuntimeError:
            pass
    finally:
        run.diagnostics()
        final_log = run.output / "logcat.txt"
        if error is None and final_log.is_file():
            error = crash_reason(final_log.read_text(encoding="utf-8", errors="replace"), args.package)
        summary = {"passed": error is None, "error": error, "seconds": round(time.monotonic() - run.started_at, 2), "screens": run.results}
        (run.output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if error is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
