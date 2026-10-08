#!/usr/bin/env python3
"""Capture real emulator screens and fail on navigation, process, crash or ANR errors.

Requires an already booted emulator and an installable debug APK. This checks the
unrooted App UI, not font replacement on HyperOS/ColorOS. Screenshots come from
real adb screencap pixels; no mock data, screenshots or crash suppression are injected.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import struct
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path

from ui_snapshot_session import UiSnapshotSession


PAGES = (
    ("home", "首页", "当前字体"),
    ("library", "字体库", "搜索你的字体"),
    ("studio", "组合", "字体组合"),
    ("settings", "设置", "你的洛书"),
)
BOUNDS = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


def canonical_component(component: str) -> str:
    package, activity = component.split("/", 1)
    return f"{package}/{package + activity if activity.startswith('.') else activity}"


def focused_component(window: str) -> str | None:
    match = re.search(r"mCurrentFocus=Window\{[^\n]*?\s([\w.$]+/[\w.$]+)\}", window)
    return canonical_component(match.group(1)) if match else None


def home_window_state(window: str) -> dict[str, object]:
    """Read explicit keyguard evidence; delegate reset defaults are unknown.

    These policy/display dumps are successive observations, not an atomic
    snapshot. Require one matching showing value and a real delegate user
    before requesting dismissal or confirming that a request completed.
    """
    evidence: dict[str, object] = {"focused_component": None}
    focuses = re.findall(r"^\s*mCurrentFocus=(.*)$", window, re.MULTILINE)
    focus = focuses[0].strip() if len(focuses) == 1 else None
    evidence["current_focus"] = focus
    evidence["focus_definition_count"] = len(focuses)
    evidence["focus_valid"] = focus == "null" or \
        (focus is not None and re.fullmatch(r"Window\{[^{}\r\n]+\}", focus) is not None)
    if evidence["focus_valid"]:
        evidence["focused_component"] = focused_component(f"mCurrentFocus={focus}")
    blocks = list(re.finditer(r"^([ \t]*)KeyguardServiceDelegate[ \t]*$", window, re.MULTILINE))
    reasons = []
    if not evidence["focus_valid"]:
        reasons.append("missing-ambiguous-or-invalid-focus")
    if len(blocks) != 1:
        reasons.append("missing-or-ambiguous-delegate")
        delegate = ""
    else:
        indentation = blocks[0].group(1)
        tail = window[blocks[0].end():].lstrip("\r\n")
        # Stop when the policy resumes at the delegate heading's indentation.
        lines = []
        for line in tail.splitlines():
            if line.strip() and len(line) - len(line.lstrip()) <= len(indentation):
                break
            lines.append(line)
        delegate = "\n".join(lines)
    for field in ("showing", "occluded", "currentUser"):
        values = re.findall(rf"^\s*{field}=([^\r\n]*)$", delegate, re.MULTILINE)
        value = values[0].strip() if len(values) == 1 else None
        parsed = int(value) if field == "currentUser" and value is not None and re.fullmatch(r"-?\d+", value) else \
            (value == "true" if field != "currentUser" and value in ("true", "false") else None)
        evidence[f"delegate_{field}"] = parsed
        if parsed is None:
            reasons.append(f"missing-or-ambiguous-{field}")
    showing = re.findall(r"^\s*isKeyguardShowing=([^\r\n]*)$", window, re.MULTILINE)
    evidence["display_showing"] = showing[0].strip() == "true" if len(showing) == 1 and \
        showing[0].strip() in ("true", "false") else None
    if evidence["display_showing"] is None:
        reasons.append("missing-or-ambiguous-display-showing")
    if evidence["delegate_currentUser"] is not None and evidence["delegate_currentUser"] < 0:
        reasons.append("delegate-user-unknown")
    if evidence["delegate_showing"] is not None and evidence["display_showing"] is not None and \
            evidence["delegate_showing"] != evidence["display_showing"]:
        reasons.append("showing-conflict")
    if evidence["delegate_occluded"]:
        reasons.append("keyguard-occluded")
    evidence["keyguard_state"] = "unknown" if reasons else \
        ("locked" if evidence["delegate_showing"] else "unlocked")
    evidence["unknown_reasons"] = reasons
    return evidence


def home_content_bounds(window: str, size: tuple[int, int]) -> tuple[int, int, int, int]:
    """Exclude only the real status/navigation source rectangles from comparison."""
    width, height = size
    top, bottom = 0, height
    status_found = navigation_found = False
    for kind, left, upper, right, lower in re.findall(
            r"type=(statusBars|navigationBars)\s+frame=\[(\d+),(\d+)\]\[(\d+),(\d+)\]", window):
        left, upper, right, lower = map(int, (left, upper, right, lower))
        if left != 0 or right != width:
            continue
        if kind == "statusBars" and upper == 0 and 0 < lower < height:
            top = max(top, lower)
            status_found = True
        elif kind == "navigationBars" and lower == height and 0 < upper < height:
            bottom = min(bottom, upper)
            navigation_found = True
    if not status_found or not navigation_found or top >= bottom:
        raise RuntimeError("Cannot identify real HOME system bars for baseline stability")
    return 0, top, width, bottom


def decode_raw_screencap(raw: bytes, api_level: int):
    """Decode only exact packed 8-bit RGB pixels; never guess a header or gamut.

    AOSP screencap writes native uint32 width/height/format and, since API 27,
    colorspace, then width * bytesPerPixel bytes per row (no stride padding).
    Android CI's x86/arm targets are little endian. See cmds/screencap/screencap.cpp
    in android-8.0.0_r1, android-8.1.0_r1 and android-16.0.0_r2.
    """
    from PIL import Image

    if type(api_level) is not int or api_level <= 0:
        raise RuntimeError("Raw screencap requires the actual Android API level")
    header_bytes = 16 if api_level >= 27 else 12
    if len(raw) < header_bytes:
        raise RuntimeError("Raw screencap header is truncated")
    width, height, pixel_format = struct.unpack_from("<III", raw)
    # After checking opaque RGBA, RGBX decoding only drops its fourth byte.
    formats = {1: (4, "RGBX"), 2: (4, "RGBX"), 3: (3, "RGB")}
    if width == 0 or height == 0 or pixel_format not in formats:
        raise RuntimeError("Raw screencap has invalid dimensions or unsupported pixel format")
    colorspace = struct.unpack_from("<I", raw, 12)[0] if header_bytes == 16 else None
    if colorspace is not None and colorspace != 1:
        raise RuntimeError("Raw screencap colorspace is not explicit sRGB")
    bytes_per_pixel, raw_mode = formats[pixel_format]
    expected = header_bytes + width * height * bytes_per_pixel
    if len(raw) != expected:
        raise RuntimeError(f"Raw screencap length mismatch: expected {expected}, received {len(raw)}")
    pixels = raw[header_bytes:]
    if pixel_format == 1 and pixels[3::4].count(255) != width * height:
        raise RuntimeError("Raw screencap contains nonopaque premultiplied RGBA pixels")
    image = Image.frombytes("RGB", (width, height), pixels, "raw", raw_mode)
    return image, {"api_level": api_level, "header_bytes": header_bytes,
                   "width": width, "height": height, "pixel_format": pixel_format,
                   "colorspace_id": colorspace, "raw_bytes": len(raw),
                   "raw_sha256": hashlib.sha256(raw).hexdigest(),
                   "rgb_sha256": hashlib.sha256(image.tobytes()).hexdigest()}


def decompress_screencap_gzip(compressed: bytes) -> bytes:
    """Accept exactly one complete gzip member with its CRC and size checked."""
    try:
        decoder = zlib.decompressobj(16 + zlib.MAX_WBITS)
        raw = decoder.decompress(compressed) + decoder.flush()
    except zlib.error as error:
        raise RuntimeError(f"Raw screencap gzip integrity failure: {error}") from error
    if not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
        raise RuntimeError("Raw screencap gzip must contain one complete member without trailing bytes")
    return raw


def home_launcher_content(root: ET.Element, home: str) -> list[dict[str, object]]:
    """Require live visible Launcher workspace/hotseat actions, beyond its splash.

    The independent snapshot reader includes view IDs and only visible children.
    An activity root, a centered logo, or actions from another package do not
    establish that the resolved Launcher has rendered its desktop content.
    """
    package = home.split("/", 1)[0]
    evidence = []
    for container in root.iter("node"):
        resource = container.get("resource-id", "")
        if container.get("package") != package or resource not in (
                f"{package}:id/workspace", f"{package}:id/hotseat"):
            continue
        try:
            container_bounds = bounds(container)
        except ValueError:
            continue
        for node in container.iter("node"):
            if node is container or node.get("package") != package or not labels(node) or \
                    node.get("clickable") != "true" or node.get("enabled") != "true":
                continue
            try:
                node_bounds = bounds(node)
            except ValueError:
                continue
            left, top, right, bottom = node_bounds
            if left < container_bounds[0] or top < container_bounds[1] or \
                    right > container_bounds[2] or bottom > container_bounds[3]:
                continue
            evidence.append({"container": resource, "bounds": list(node_bounds),
                             "labels": sorted(labels(node))})
    return evidence


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


def app_labels(root: ET.Element, package: str) -> set[str]:
    return {value for node in root.iter("node") if node.get("package") == package for value in labels(node)}


def label_target(root: ET.Element, label: str, package: str) -> ET.Element:
    """Resolve a label to its enabled, visible semantic action, never a text guess."""
    parents = {child: parent for parent in root.iter() for child in parent}
    targets = []
    for node in root.iter("node"):
        if node.get("package") != package or label not in labels(node):
            continue
        ancestors = []
        ancestor = node
        while ancestor is not None:
            ancestors.append(ancestor)
            ancestor = parents.get(ancestor)
        if any(ancestor.get("enabled") == "false" for ancestor in ancestors):
            continue
        candidate = node
        while candidate is not None and candidate.get("package") == package:
            try:
                bounds(candidate)
            except ValueError:
                candidate = parents.get(candidate)
                continue
            if candidate.get("enabled") != "false" and (
                candidate.get("clickable") == "true"
                or candidate.get("checkable") == "true"
                or candidate.get("selected") == "true" and candidate.get("focusable") == "true"
            ):
                targets.append(candidate)
                break
            candidate = parents.get(candidate)
    if not targets:
        raise ValueError(f"Enabled action for {label!r} not found in the App hierarchy")
    return min(targets, key=lambda node: (bounds(node)[2] - bounds(node)[0]) * (bounds(node)[3] - bounds(node)[1]))


def choice_selected(root: ET.Element, label: str, package: str) -> bool:
    try:
        target = label_target(root, label, package)
    except ValueError:
        return False
    return target.get("selected") == "true" or target.get("checked") == "true"


def action_disabled(root: ET.Element, label: str, package: str) -> bool:
    parents = {child: parent for parent in root.iter() for child in parent}
    for node in root.iter("node"):
        if node.get("package") != package or label not in labels(node):
            continue
        candidate = node
        while candidate is not None and candidate.get("package") == package:
            if candidate.get("enabled") == "false":
                return True
            candidate = parents.get(candidate)
    return False


def content_anchors(root: ET.Element, package: str) -> dict[str, tuple[int, int]]:
    """Visible text positions, excluding navigation, for actual scroll preservation."""
    rectangles = []
    for node in root.iter("node"):
        if node.get("package") == package:
            try:
                rectangles.append(bounds(node))
            except ValueError:
                pass
    if not rectangles:
        raise ValueError("App bounds not found in the hierarchy")
    bottom = max(rect[3] for rect in rectangles)
    navigation = {page[1] for page in PAGES}
    anchors = {}
    duplicates = set()
    for node in root.iter("node"):
        if node.get("package") != package:
            continue
        try:
            position = center(node)
        except ValueError:
            continue
        if not bottom * .12 < position[1] < bottom * .82:
            continue
        for label in labels(node) - navigation:
            if label in anchors:
                duplicates.add(label)
            anchors[label] = position
    return {label: position for label, position in anchors.items() if label not in duplicates}


def anchors_preserved(before: dict[str, tuple[int, int]], after: dict[str, tuple[int, int]], tolerance: int = 12) -> bool:
    return bool(before) and all(
        label in after and all(abs(left - right) <= tolerance for left, right in zip(position, after[label]))
        for label, position in before.items()
    )


def app_window_bounds(root: ET.Element, package: str) -> tuple[int, int, int, int]:
    """Use the real accessibility window, not physical screenshot dimensions."""
    parents = {child: parent for parent in root.iter() for child in parent}
    windows = []
    for node in root.iter("node"):
        if node.get("package") != package or parents.get(node, root).get("package") == package:
            continue
        try:
            windows.append(bounds(node))
        except ValueError:
            pass
    if not windows:
        raise RuntimeError("No visible App accessibility window for a scroll gesture")
    return max(windows, key=lambda rect: (rect[2] - rect[0]) * (rect[3] - rect[1]))


def logical_input_size(wm_size: str, window: tuple[int, int, int, int],
                       root: ET.Element) -> tuple[int, int]:
    """Rotate the logical wm display from snapshot metadata, never from modal shape."""
    rotation = root.get("rotation")
    if root.tag != "hierarchy" or rotation not in ("0", "1", "2", "3"):
        raise RuntimeError(f"Cannot verify actual display rotation from complete snapshot: {rotation!r}")
    sizes = {
        kind: (int(width), int(height))
        for kind, width, height in re.findall(r"(Physical|Override) size:\s*(\d+)x(\d+)", wm_size)
    }
    size = sizes.get("Override", sizes.get("Physical"))
    if size is None:
        raise RuntimeError(f"Cannot verify logical input dimensions from adb wm size: {wm_size.strip()}")
    width, height = size
    if rotation in ("1", "3"):
        width, height = height, width
    if window[0] < 0 or window[1] < 0 or window[2] > width or window[3] > height:
        raise RuntimeError(f"App hierarchy window {window} exceeds logical input display {width}x{height}")
    return width, height


def scroll_content(root: ET.Element, package: str) -> tuple[ET.Element, tuple[int, int, int, int]]:
    """Choose the vertical content container, excluding horizontal chip rows and dock."""
    window = app_window_bounds(root, package)
    candidates = []
    for node in root.iter("node"):
        if node.get("package") != package or node.get("scrollable") != "true":
            continue
        try:
            rect = bounds(node)
        except ValueError:
            continue
        rect = (max(rect[0], window[0]), max(rect[1], window[1]),
                min(rect[2], window[2]), min(rect[3], window[3]))
        if rect[2] > rect[0] and rect[3] - rect[1] >= (window[3] - window[1]) * .25:
            candidates.append((node, rect))
    if not candidates:
        raise RuntimeError("No visible vertical App scroll container")
    node, rect = max(candidates, key=lambda item: (item[1][2] - item[1][0]) * (item[1][3] - item[1][1]))
    # Older Android exposes these Decor-owned bars in the App window tree. They
    # remain outside content even when screencap returns a letterboxed surface.
    for bar in root.iter("node"):
        if bar.get("resource-id") not in ("android:id/navigationBarBackground", "android:id/statusBarBackground"):
            continue
        try:
            left, top, right, bottom = bounds(bar)
        except ValueError:
            continue
        if left <= rect[0] and right >= rect[2]:
            if top <= rect[1] < bottom < rect[3]:
                rect = (rect[0], bottom, rect[2], rect[3])
            elif rect[1] < top < rect[3] <= bottom:
                rect = (*rect[:3], top)
        elif top <= rect[1] and bottom >= rect[3]:
            if left <= rect[0] < right < rect[2]:
                rect = (right, rect[1], rect[2], rect[3])
            elif rect[0] < left < rect[2] <= right:
                rect = (rect[0], rect[1], left, rect[3])
    try:
        dock_top = min(bounds(tab_target(root, label, package))[1] for _, label, _ in PAGES)
        if rect[1] < dock_top < rect[3]:
            rect = (*rect[:3], dock_top)
    except ValueError:
        pass  # Detail pages legitimately have no dock.
    if rect[3] - rect[1] < 80 or rect[2] - rect[0] < 40:
        raise RuntimeError("Visible App scroll content is too small for a safe gesture")
    return node, rect


def visible_scroll_anchors(root: ET.Element, package: str) -> dict[str, tuple[int, int]]:
    node, rect = scroll_content(root, package)
    anchors: dict[str, tuple[int, int]] = {}
    duplicates = set()
    for child in node.iter("node"):
        if child.get("package") != package:
            continue
        try:
            position = center(child)
        except ValueError:
            continue
        if not (rect[0] <= position[0] < rect[2] and rect[1] <= position[1] < rect[3]):
            continue
        for label in labels(child) - {page[1] for page in PAGES}:
            if label in anchors:
                duplicates.add(label)
            anchors[label] = position
    return {label: position for label, position in anchors.items() if label not in duplicates}


def scroll_progress(before: dict[str, tuple[int, int]], after: dict[str, tuple[int, int]],
                    direction: str, tolerance: int = 12) -> bool:
    if direction not in ("up", "down"):
        raise ValueError(f"Unknown scroll direction: {direction}")
    shared = set(before) & set(after)
    deltas = [after[label][1] - before[label][1] for label in shared]
    if deltas:
        expected = (lambda delta: delta < -tolerance) if direction == "up" else (lambda delta: delta > tolerance)
        return any(expected(delta) for delta in deltas) and not any(expected(-delta) for delta in deltas)
    # A full viewport replacement is real content evidence, not a node count.
    return bool(before and after and set(before) != set(after))


def visible_action(root: ET.Element, label: str, package: str) -> ET.Element:
    target = label_target(root, label, package)
    _, rect = scroll_content(root, package)
    left, top, right, bottom = bounds(target)
    if not (rect[0] <= left < right <= rect[2] and rect[1] <= top < bottom <= rect[3]):
        raise ValueError(f"Enabled action for {label!r} is outside visible scroll content")
    return target


def visible_control(root: ET.Element, label: str, package: str) -> ET.Element:
    """Require a whole semantic control and label above the dock; disabled is valid."""
    content, rect = scroll_content(root, package)
    parents = {child: parent for parent in root.iter() for child in parent}
    for node in content.iter("node"):
        if node.get("package") != package or label not in labels(node):
            continue
        target = node
        while target is not None and target is not content and target.get("package") == package:
            if target.get("clickable") == "true" or target.get("checkable") == "true" or (
                    target.get("selected") == "true" and target.get("focusable") == "true"):
                try:
                    control = bounds(target)
                    text = bounds(node)
                except ValueError:
                    break
                if (rect[0] <= control[0] < control[2] <= rect[2]
                        and rect[1] <= control[1] < control[3] <= rect[3]
                        and control[0] <= text[0] < text[2] <= control[2]
                        and control[1] <= text[1] < text[3] <= control[3]):
                    return target
                break
            target = parents.get(target)
    raise ValueError(f"Whole control for {label!r} is outside visible scroll content or absent")


def visible_text(root: ET.Element, marker: str, package: str) -> bool:
    _, rect = scroll_content(root, package)
    for node in root.iter("node"):
        if node.get("package") != package or not any(marker in value for value in labels(node)):
            continue
        try:
            x, y = center(node)
        except ValueError:
            continue
        if rect[0] <= x < rect[2] and rect[1] <= y < rect[3]:
            return True
    return False


class ScrollBudget:
    """A shared hard search budget, including waits and all stages of a help flow."""
    def __init__(self, timeout: float = 90, max_gestures: int = 8):
        if timeout <= 0 or max_gestures < 0:
            raise ValueError("Scroll search requires a positive timeout and nonnegative gesture budget")
        self.deadline = time.monotonic() + timeout
        self.max_gestures = max_gestures
        self.used = 0


def library_state_preserved(root: ET.Element, before: dict[str, tuple[int, int]], package: str) -> bool:
    """Require the real page, selected filter and every saved visible anchor."""
    return (page_ready(root, "字体库", "筛选结果", package)
            and choice_selected(root, "收藏", package)
            and anchors_preserved(before, content_anchors(root, package)))


def legacy_manual_colors_ready(root: ET.Element, package: str) -> bool:
    texts = app_labels(root, package)
    if ("当前系统不支持壁纸取色，可直接选择主题色。" not in texts
            or any("已跟随壁纸取色" in text for text in texts)):
        return False
    try:
        return all(label_target(root, label, package).get("enabled") != "false" for label in ("曜紫", "青蓝"))
    except ValueError:
        return False


def legacy_monet_unavailable(root: ET.Element, package: str) -> bool:
    return ("需要 Android 12 或更高版本，当前可手动选色" in app_labels(root, package)
            and action_disabled(root, "Monet 动态取色", package))


def orientation_matches(root: ET.Element, package: str, landscape: bool) -> bool:
    rectangles = []
    for node in root.iter("node"):
        if node.get("package") == package:
            try:
                rectangles.append(bounds(node))
            except ValueError:
                pass
    if not rectangles:
        return False
    width, height = max(rect[2] for rect in rectangles), max(rect[3] for rect in rectangles)
    return width > height if landscape else height > width


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


def instrumentation_results(output: str) -> dict[str, str]:
    return dict(re.findall(r"^INSTRUMENTATION_RESULT: ([A-Za-z_]\w*)=(.*)$", output, re.MULTILINE))


def assert_single_stage_startup(log: str, pid: str, api_level: int) -> list[str]:
    """Require current-process content delivery; visual handoff needs decoded frames.

    Default platform removal has no App exit callback. Absence of art/native event
    names cannot establish what was actually composited over the home screen.
    """
    events = re.findall(
        rf"^\S+\s+\S+\s+{re.escape(pid)}\s+\d+\s+I\s+LuoShuStartup\s*:\s+event=(\w+)",
        log, re.MULTILINE,
    )
    if any(event.startswith("art_") for event in events):
        raise RuntimeError("A second branded App launch layer was reported")
    for event in ("first_decor_draw", "content_draw_delivered", "launch_complete"):
        if event not in events:
            raise RuntimeError(f"Current launch is missing startup evidence: {event}")
    return events


class SmokeRun:
    def __init__(self, apk: Path, output: Path, package: str, serial: str | None, snapshot_apk: Path | None = None,
                 record_launch: bool = False, visual_launch_only: bool = False, snapshot_child_prefetch: str = "zero"):
        if snapshot_child_prefetch not in ("zero", "default"):
            raise ValueError("Invalid child prefetch mode")
        if snapshot_child_prefetch == "default" and not visual_launch_only:
            raise ValueError("Default child prefetch experiment requires visual-launch-only")
        self.apk = apk
        self.output = output
        self.package = package
        self.adb_command = ["adb"] + (["-s", serial] if serial else [])
        self.output.mkdir(parents=True, exist_ok=True)
        self.results: list[dict[str, object]] = []
        self.checks: list[dict[str, object]] = []
        self.recordings: list[dict[str, object]] = []
        self.record_launch = record_launch
        self.visual_launch_only = visual_launch_only
        self.api_level: int | None = None
        self.snapshot_apk = snapshot_apk
        self.snapshot_child_prefetch = snapshot_child_prefetch
        self.snapshot_session: UiSnapshotSession | None = None
        self.hierarchy_attempts = 0
        self.scroll_searches = 0
        self.hierarchy_backend = "uiautomator-cli"
        self.started_at = time.monotonic()
        self.adb_command_count = 0
        self.adb_diagnostic_errors: list[str] = []

    def _record_adb(self, record: dict[str, object], stdout: bytes, stderr: bytes) -> None:
        """Keep complete command streams; console error excerpts are not evidence."""
        prefix = f"adb-command-{record['index']:04d}"
        for stream, data in (("stdout", stdout), ("stderr", stderr)):
            filename = f"{prefix}-{stream}.bin"
            record[stream] = filename
            record[f"{stream}_bytes"] = len(data)
            record[f"{stream}_sha256"] = hashlib.sha256(data).hexdigest()
            (self.output / filename).write_bytes(data)
        record["raw_streams_written_monotonic_seconds"] = time.monotonic()
        with (self.output / "adb-commands.jsonl").open("a", encoding="utf-8") as evidence:
            evidence.write(json.dumps(record, ensure_ascii=False) + "\n")

    def adb(self, *arguments: str, timeout: float = 20, check: bool = True) -> subprocess.CompletedProcess[bytes]:
        self.adb_command_count += 1
        command = self.adb_command + list(arguments)
        record: dict[str, object] = {"index": self.adb_command_count, "arguments": command,
                                    "timeout_seconds": timeout, "check": check,
                                    "started_unix_seconds": time.time(),
                                    "started_monotonic_seconds": time.monotonic()}
        stdout = stderr = b""
        try:
            result = subprocess.run(command, capture_output=True, timeout=timeout)
            stdout, stderr = result.stdout, result.stderr
            record.update({"outcome": "returned", "returncode": result.returncode})
        except subprocess.TimeoutExpired as error:
            # subprocess.run kills and waits for its child before raising. Its
            # exception keeps the bytes received before timeout, without a
            # reliable child returncode. Preserve them before chaining the error.
            stdout, stderr = error.output or b"", error.stderr or b""
            record.update({"outcome": "timed-out", "returncode": None,
                           "partial_streams": True, "error": f"{type(error).__name__}: {error}"})
            raise RuntimeError(f"adb timed out after {timeout}s: {' '.join(arguments)}") from error
        except OSError as error:
            record.update({"outcome": "exception", "returncode": None,
                           "error": f"{type(error).__name__}: {error}"})
            raise
        finally:
            ended = time.monotonic()
            record.setdefault("outcome", "interrupted")
            record.setdefault("returncode", None)
            record.update({"ended_monotonic_seconds": ended,
                           "elapsed_seconds": ended - record["started_monotonic_seconds"],
                           "ended_unix_seconds": time.time()})
            # Record only after the actual command. Diagnostic I/O still counts
            # toward callers' existing absolute deadlines; no timeout is reset.
            try:
                self._record_adb(record, stdout, stderr)
            except Exception as error:
                diagnostic = f"adb command {record['index']} evidence {type(error).__name__}: {error}"
                self.adb_diagnostic_errors.append(diagnostic)
                print(diagnostic, file=sys.stderr, flush=True)
        if check and result.returncode:
            detail = (result.stdout + result.stderr).decode("utf-8", "replace")[-3_000:]
            raise RuntimeError(f"adb {' '.join(arguments)} failed ({result.returncode}): {detail}")
        return result

    def text(self, *arguments: str, **kwargs: object) -> str:
        return self.adb(*arguments, **kwargs).stdout.decode("utf-8", "replace")

    def hierarchy(self) -> ET.Element:
        # A live UiAutomation connection can briefly expose only the Decor root
        # after a display/configuration change (API 28 CI hierarchy-0042). Keep
        # that raw snapshot, but wait for real descendants before using it as
        # evidence that an action or a scroll container is absent.
        started = time.monotonic()
        deadline = started + 8
        rejected = []
        try:
            while True:
                root = self.hierarchy_once()
                if len(list(root.iter("node"))) > 1:
                    return root
                rejected.append({"xml": f"hierarchy-{self.hierarchy_attempts:04d}.xml",
                                 "elapsed_seconds": round(time.monotonic() - started, 3),
                                 "reason": "Accessibility hierarchy contains only the window root"})
                self.assert_running()
                if time.monotonic() >= deadline:
                    raise RuntimeError("Real accessibility content did not become ready within 8s: window root only")
                time.sleep(.3)
        finally:
            if rejected:
                (self.output / f"hierarchy-readiness-{self.hierarchy_attempts:04d}.json").write_text(
                    json.dumps({"rejected_snapshots": rejected,
                                "elapsed_seconds": round(time.monotonic() - started, 3)}, indent=2) + "\n",
                    encoding="utf-8")

    def hierarchy_once(self) -> ET.Element:
        self.hierarchy_attempts += 1
        if self.hierarchy_backend == "ui-automation-snapshot":
            return self.snapshot_hierarchy()
        remote = "/sdcard/luoshu-ui-smoke.xml"
        self.adb("shell", "rm", "-f", remote)
        started = time.monotonic()
        failure = None
        try:
            dumped = self.adb("shell", "uiautomator", "dump", remote, timeout=15, check=False)
            stdout = dumped.stdout.decode("utf-8", "replace")
            stderr = dumped.stderr.decode("utf-8", "replace")
            evidence = {"attempt": self.hierarchy_attempts, "returncode": dumped.returncode,
                        "seconds": round(time.monotonic() - started, 3), "stdout": stdout, "stderr": stderr}
            (self.output / f"hierarchy-dump-{self.hierarchy_attempts:04d}.json").write_text(
                json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            if dumped.returncode or re.search(r"\bERROR:", stdout + stderr):
                failure = f"uiautomator dump returned {dumped.returncode}: {(stdout + stderr).strip()}"
            result = self.adb("shell", "cat", remote, check=False)
            if result.returncode:
                failure = failure or f"uiautomator returned {dumped.returncode} without creating {remote}: {(stdout + stderr).strip()}"
                (self.output / f"hierarchy-read-{self.hierarchy_attempts:04d}.txt").write_bytes(result.stdout + result.stderr)
            elif failure is None:
                xml = result.stdout.decode("utf-8", "replace")
                root = ET.fromstring(xml)
                (self.output / f"hierarchy-{self.hierarchy_attempts:04d}.xml").write_text(xml, encoding="utf-8")
                (self.output / "latest-hierarchy.xml").write_text(xml, encoding="utf-8")
                return root
        except (RuntimeError, ET.ParseError) as error:
            failure = str(error)
            (self.output / f"hierarchy-dump-{self.hierarchy_attempts:04d}-failure.txt").write_text(failure + "\n", encoding="utf-8")
        # Preserve a same-UID storage probe to distinguish a non-idle CLI from a
        # missing or unwritable shared storage path; never infer the cause from exit 0.
        probe = remote + ".probe"
        touched = self.adb("shell", "touch", probe, check=False)
        listed = self.adb("shell", "ls", "-l", probe, check=False)
        self.adb("shell", "rm", "-f", probe, check=False)
        (self.output / f"hierarchy-storage-probe-{self.hierarchy_attempts:04d}.json").write_text(
            json.dumps({"path": probe, "touch_returncode": touched.returncode,
                        "touch_output": (touched.stdout + touched.stderr).decode("utf-8", "replace"),
                        "list_returncode": listed.returncode,
                        "list_output": (listed.stdout + listed.stderr).decode("utf-8", "replace")},
                       ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if self.snapshot_apk is not None:
            self.hierarchy_backend = "ui-automation-snapshot"
            root = self.snapshot_hierarchy()
            self.checks.append({"check": "hierarchy-reader-fallback", "passed": True,
                                "reason": failure, "backend": self.hierarchy_backend})
            return root
        raise RuntimeError(failure or "uiautomator did not produce a valid live hierarchy")

    def snapshot_hierarchy(self, *, deadline: float | None = None) -> ET.Element:
        filename = f"hierarchy-{self.hierarchy_attempts:04d}.xml"
        if self.snapshot_session is None:
            self.snapshot_session = UiSnapshotSession(self.adb_command, self.output,
                child_prefetch_mode=self.snapshot_child_prefetch, expected_api_level=self.api_level)
        metadata, xml = (self.snapshot_session.capture(filename) if deadline is None else
                         self.snapshot_session.capture(filename, deadline=deadline))
        evidence = {"transport": "persistent-ui-automation", "session_nonce": self.snapshot_session.nonce,
                    **metadata}
        (self.output / f"hierarchy-snapshot-{self.hierarchy_attempts:04d}.json").write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        if metadata.get("snapshot") != "ok" or xml is None:
            raise RuntimeError("Real UiAutomation snapshot failed: " + json.dumps(metadata, ensure_ascii=False))
        root = ET.fromstring(xml)
        if root.tag != "hierarchy" or not list(root.iter("node")):
            raise RuntimeError("Real UiAutomation snapshot contains no accessible window nodes")
        (self.output / filename).write_text(xml, encoding="utf-8")
        (self.output / "latest-hierarchy.xml").write_text(xml, encoding="utf-8")
        return root

    def close_snapshot_session(self) -> None:
        if self.snapshot_session is not None:
            self.snapshot_session.close()

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

    def wait_ui(self, predicate, description: str, timeout: float = 30) -> ET.Element:
        deadline = time.monotonic() + timeout
        last_error = description
        while time.monotonic() < deadline:
            self.assert_running()
            try:
                root = self.hierarchy()
                if predicate(root):
                    return root
            except (RuntimeError, ValueError, ET.ParseError) as error:
                last_error = str(error)
            time.sleep(.3)
        raise RuntimeError(f"{description} did not become ready within {timeout}s: {last_error}")

    def tap_label(self, label: str, *, scroll_attempts: int = 0, direction: str = "up") -> ET.Element:
        for attempt in range(scroll_attempts + 1):
            root = self.hierarchy()
            try:
                target = label_target(root, label, self.package)
            except ValueError:
                if attempt == scroll_attempts:
                    raise
                self.scroll(root, direction)
                continue
            x, y = center(target)
            self.adb("shell", "input", "tap", str(x), str(y))
            return root
        raise RuntimeError(f"Action {label!r} was not tapped")

    def select_tab(self, label: str, marker: str | None = None) -> ET.Element:
        root = self.ensure_dock()
        x, y = center(tab_target(root, label, self.package))
        self.adb("shell", "input", "tap", str(x), str(y))
        if marker is not None:
            return self.wait_page(label, marker)
        return self.wait_ui(
            lambda root: any(node.get("selected") == "true" for node in tab_target(root, label, self.package).iter()),
            f"Selected tab {label!r}",
        )

    def ensure_dock(self) -> ET.Element:
        root = self.hierarchy()
        try:
            tab_target(root, "首页", self.package)
            return root
        except ValueError:
            # Production Quick Return hides the dock after a real content scroll.
            # A short downward gesture reveals it; do not tap invisible coordinates.
            started = time.monotonic()
            deadline = started + 30
            self.quick_return_attempts = getattr(self, "quick_return_attempts", 0) + 1
            prefix = f"quick-return-{self.quick_return_attempts:04d}"
            before_xml = f"{prefix}-before.xml"
            after_xml = f"{prefix}-after.xml"
            ET.ElementTree(root).write(self.output / before_xml, encoding="utf-8", xml_declaration=True)
            evidence = {"passed": False, "timeout_seconds": 30, "before_xml": before_xml,
                        "after_xml": after_xml, "before_anchors": {}, "after_snapshot_received": False}
            try:
                evidence["before_anchors"] = content_anchors(root, self.package)
            except ValueError as error:
                evidence["before_anchor_error"] = str(error)
            last_root = root

            def dock_ready(current: ET.Element) -> bool:
                nonlocal last_root
                last_root = current
                evidence["after_snapshot_received"] = True
                return tab_target(current, "首页", self.package) is not None

            try:
                rectangles = []
                for node in root.iter("node"):
                    if node.get("package") != self.package:
                        continue
                    try:
                        rectangles.append(bounds(node))
                    except ValueError:
                        # A clipped offscreen descendant is not a gesture target.
                        # Keep strict bounds for every actual navigation target
                        # and refuse the gesture if no real App rectangle exists.
                        continue
                if not rectangles:
                    raise RuntimeError("Cannot read actual App bounds for Quick Return")
                width, height = max(rect[2] for rect in rectangles), max(rect[3] for rect in rectangles)
                x, start, end = width // 2, int(height * .40), int(height * .46)
                evidence["gesture"] = {"from": [x, start], "to": [x, end], "duration_ms": 2000}
                gesture_started = time.monotonic()
                # input swipe synchronously injects DOWN before its timed MOVE loop.
                # A 300ms gesture can lose every MOVE while HWUI blocks that DOWN.
                try:
                    self.adb("shell", "input", "swipe", str(x), str(start), str(x), str(end), "2000")
                finally:
                    evidence["gesture_elapsed_seconds"] = round(time.monotonic() - gesture_started, 3)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RuntimeError("Quick Return navigation exhausted its 30s budget during the gesture")
                ready = self.wait_ui(dock_ready, "Quick Return navigation", timeout=remaining)
                dock_ready(ready)
                evidence["navigation"] = {
                    label: {"bounds": bounds(target), "selected": target.get("selected"),
                            "clickable": target.get("clickable"), "enabled": target.get("enabled")}
                    for _, label, _ in PAGES for target in [tab_target(ready, label, self.package)]
                }
                evidence["passed"] = True
                return ready
            except Exception as error:
                evidence["error"] = f"{type(error).__name__}: {error}"
                raise
            finally:
                ET.ElementTree(last_root).write(self.output / after_xml, encoding="utf-8", xml_declaration=True)
                try:
                    evidence["after_anchors"] = content_anchors(last_root, self.package)
                except ValueError as error:
                    evidence["after_anchors"] = {}
                    evidence["after_anchor_error"] = str(error)
                evidence["elapsed_seconds"] = round(time.monotonic() - started, 3)
                (self.output / f"{prefix}.json").write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n",
                                                         encoding="utf-8")

    def reach_content(self, predicate, description: str, *, direction: str = "up",
                      budget: ScrollBudget | None = None, root: ET.Element | None = None) -> ET.Element:
        """Reach an actual visible predicate; stop hard on no progress, time or gesture limits."""
        if direction not in ("up", "down"):
            raise ValueError(f"Unknown scroll direction: {direction}")
        budget = budget or ScrollBudget()
        self.scroll_searches += 1
        prefix = f"scroll-search-{self.scroll_searches:04d}"
        started = time.monotonic()
        samples = []
        wm_size = self.text("shell", "wm", "size")
        metadata = {"description": description, "direction": direction, "wm_size": wm_size,
                    "max_gestures": budget.max_gestures, "samples": samples, "passed": False}

        def save(current: ET.Element, phase: str, **extra: object) -> dict[str, tuple[int, int]]:
            filename = f"{prefix}-{len(samples):03d}.xml"
            ET.ElementTree(current).write(self.output / filename, encoding="utf-8", xml_declaration=True)
            window = app_window_bounds(current, self.package)
            input_size = logical_input_size(wm_size, window, current)
            _, rect = scroll_content(current, self.package)
            anchors = visible_scroll_anchors(current, self.package)
            samples.append({"phase": phase, "xml": filename, "elapsed_seconds": round(time.monotonic() - started, 3),
                            "input_size": input_size, "rotation": current.get("rotation"),
                            "window_bounds": window, "content_bounds": rect,
                            "anchors": anchors, "gestures_used": budget.used, **extra})
            return anchors

        def ready(current: ET.Element) -> bool:
            try:
                result = predicate(current)
                return result is not None if isinstance(result, ET.Element) else bool(result)
            except ValueError:
                return False

        try:
            current = root if root is not None else self.hierarchy()
            before = save(current, "initial")
            while True:
                self.assert_running()
                if time.monotonic() >= budget.deadline:
                    raise RuntimeError(f"{description}: total scroll search time budget exhausted")
                if ready(current):
                    metadata["passed"] = True
                    return current
                if budget.used >= budget.max_gestures:
                    raise RuntimeError(f"{description}: scroll gesture budget exhausted before the visible target")
                if not before:
                    raise RuntimeError(f"{description}: no visible content anchors to establish scroll progress")
                _, rect = scroll_content(current, self.package)
                x = (rect[0] + rect[2]) // 2
                low, high = rect[1] + int((rect[3] - rect[1]) * .25), rect[1] + int((rect[3] - rect[1]) * .76)
                start, end = (high, low) if direction == "up" else (low, high)
                budget.used += 1
                # The software-rendered API 36 emulator recorded 1.2s frames:
                # a 400ms drag moved only ~150px of a requested 1360px. Give one
                # real drag time to deliver its motion while retaining the same
                # live bounds, shared gesture/time limits and progress checks.
                gesture = {"from": [x, start], "to": [x, end], "duration_ms": 2000}
                self.adb("shell", "input", "swipe", str(x), str(start), str(x), str(end), "2000")
                progress_deadline = min(budget.deadline, time.monotonic() + 12)
                moved = False
                settled = False
                previous = before
                for _ in range(8):
                    if time.monotonic() >= progress_deadline:
                        break
                    time.sleep(.25)
                    self.assert_running()
                    current = self.hierarchy()
                    after = save(current, "after-gesture", gesture=gesture)
                    if time.monotonic() >= budget.deadline:
                        raise RuntimeError(f"{description}: total scroll search time budget exhausted")
                    if ready(current):
                        metadata["passed"] = True
                        return current
                    moved = moved or scroll_progress(before, after, direction)
                    settled = bool(moved and set(previous) == set(after) and anchors_preserved(previous, after, tolerance=4))
                    previous = after
                    if settled:
                        before = after
                        break
                if not moved:
                    raise RuntimeError(f"{description}: scroll stalled or reached a boundary without the visible target")
                if not settled:
                    raise RuntimeError(f"{description}: visible scroll content did not settle within the progress deadline")
        except Exception as error:
            metadata["error"] = str(error)
            raise
        finally:
            metadata["gestures_used"] = budget.used
            metadata["elapsed_seconds"] = round(time.monotonic() - started, 3)
            (self.output / f"{prefix}.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def find_choice(self, label: str, *, scroll_attempts: int = 8, direction: str = "up") -> ET.Element:
        root = self.reach_content(lambda current: visible_action(current, label, self.package),
                                  f"Saved choice {label!r}", direction=direction,
                                  budget=ScrollBudget(timeout=90, max_gestures=scroll_attempts))
        if not choice_selected(root, label, self.package):
            raise RuntimeError(f"Saved choice {label!r} is no longer selected")
        return root

    def scroll(self, root: ET.Element, direction: str = "up") -> None:
        window = app_window_bounds(root, self.package)
        logical_input_size(self.text("shell", "wm", "size"), window, root)
        _, rect = scroll_content(root, self.package)
        x = (rect[0] + rect[2]) // 2
        height = rect[3] - rect[1]
        start, end = rect[1] + int(height * .76), rect[1] + int(height * .25)
        if direction == "down":
            start, end = end, start
        elif direction != "up":
            raise ValueError(f"Unknown scroll direction: {direction}")
        self.adb("shell", "input", "swipe", str(x), str(start), str(x), str(end), "400")

    def record(self, name: str, **evidence: object) -> None:
        self.checks.append({"check": name, "passed": True, **evidence})
        print(f"Verified {name}", flush=True)

    def launch(self, name: str) -> ET.Element:
        if self.record_launch:
            baseline = self.wait_home_baseline(name) if self.visual_launch_only else self.adb("exec-out", "screencap", "-p").stdout
            (self.output / f"{name}-before.png").write_bytes(baseline)
        recording = self.begin_launch_recording(name) if self.record_launch else None
        root = None
        try:
            root = self.launch_and_capture(name)
        finally:
            if recording is not None:
                self.finish_launch_recording(recording, name)
        if self.visual_launch_only:
            evidence = next((item for item in reversed(self.recordings) if item.get("recording") == name), {})
            if not evidence.get("available"):
                raise RuntimeError(f"Required startup visual recording is unavailable: {name}")
            from android_startup_visual import inspect_recording
            result = inspect_recording(self.output / f"{name}.mp4", self.output / f"{name}-home.png",
                self.output / f"{name}-home.xml", "dark" if name.startswith("dark-") or name == "repeat-cold-start" else "light",
                self.output / f"{name}-visual-verdict.json", baseline=self.output / f"{name}-before.png", warm="warm" in name)
            if not result["passed"]:
                raise RuntimeError(f"Startup visual handoff failed for {name}: " + "; ".join(result["errors"][:8]))
            self.record(f"{name}-visual-handoff", frames_decoded=result["frames_decoded"],
                        verdict=f"{name}-visual-verdict.json", scope=result["scope"])
        return root

    def wait_home_baseline(self, name: str) -> bytes:
        """Require real Launcher content and three stable captures within 10s."""

        started = time.monotonic()
        deadline = started + 10
        metadata: dict[str, object] = {"timeout_seconds": 10, "required_stable_captures": 3, "samples": [],
                                      "started_monotonic_seconds": started, "deadline_monotonic_seconds": deadline,
                                      "clock_scope": "host time.monotonic; not aligned with native uptime"}
        previous = None
        stable = 0
        separator = b"\x00LUOSHU_HOME_BASELINE_RAW_GZIP\x00"
        state_command = "dumpsys window policy && dumpsys window displays"
        command = (r"set -o pipefail || exit; " + state_command + " && " +
                   r"printf '\000LUOSHU_HOME_BASELINE_RAW_GZIP\000' && screencap | gzip -1")
        metadata["capture_command"] = command
        metadata["screenshot_source"] = "real packed screencap through lossless device gzip -1; exact RGB PNG encoding on host"
        pending_sample = None

        def remaining() -> float:
            value = deadline - time.monotonic()
            if value <= 0:
                raise RuntimeError("HOME baseline did not become focused and stable within 10s")
            return value

        def bounded_command(key: str, arguments: tuple[str, ...],
                            extra: dict[str, object] | None = None) -> subprocess.CompletedProcess[bytes]:
            command_started = time.monotonic()
            detail = {"arguments": list(arguments), "stdout": f"{name}-baseline-{key}-stdout.bin",
                      "stderr": f"{name}-baseline-{key}-stderr.bin",
                      "started_monotonic_seconds": command_started,
                      "started_elapsed_seconds": round(command_started - started, 6),
                      "timeout_seconds": remaining(),
                      "scope": "host adb call interval including command evidence I/O, within the original HOME deadline; no native clock alignment"}
            detail.update(extra or {})
            metadata[key] = detail
            stdout = stderr = b""
            failure = None
            try:
                result = self.adb(*arguments, timeout=detail["timeout_seconds"], check=False)
                stdout, stderr = result.stdout, result.stderr
                detail.update(outcome="returned", returncode=result.returncode)
                return result
            except Exception as error:
                failure = error
                cause = error if isinstance(error, subprocess.TimeoutExpired) else error.__cause__
                detail.update(outcome="exception", error=f"{type(error).__name__}: {error}")
                if isinstance(cause, subprocess.TimeoutExpired):
                    stdout = cause.stdout if isinstance(cause.stdout, bytes) else b""
                    stderr = cause.stderr if isinstance(cause.stderr, bytes) else b""
                    detail.update(outcome="timed-out", partial_streams=True,
                                  cause=f"{type(cause).__name__}: {cause}")
                raise
            finally:
                ended = time.monotonic()
                detail.update(ended_monotonic_seconds=ended,
                              ended_elapsed_seconds=round(ended - started, 6),
                              command_seconds=round(ended - command_started, 6))
                persistence_started = time.monotonic()
                try:
                    for stream, data in (("stdout", stdout), ("stderr", stderr)):
                        (self.output / detail[stream]).write_bytes(data)
                        detail[f"{stream}_bytes"] = len(data)
                        detail[f"{stream}_sha256"] = hashlib.sha256(data).hexdigest()
                except Exception as error:
                    detail["persistence_error"] = f"{type(error).__name__}: {error}"
                    if failure is None:
                        raise
                finally:
                    persisted = time.monotonic()
                    detail["persistence_finished_elapsed_seconds"] = round(persisted - started, 6)
                    detail["persistence_seconds"] = round(persisted - persistence_started, 6)

        def observe_keyguard(state: dict[str, object], observation: str) -> None:
            dismissal = metadata.get("keyguard_dismissal")
            if dismissal is not None:
                if state["keyguard_state"] == "unlocked" and not dismissal.get("completed") and \
                        state["delegate_currentUser"] == dismissal["trigger_state"]["delegate_currentUser"]:
                    dismissal.update(completed=True, completion_observation=observation,
                                     completed_elapsed_seconds=round(time.monotonic() - started, 6))
                return
            if state["keyguard_state"] != "locked":
                return
            result = bounded_command("keyguard_dismissal", ("shell", "wm", "dismiss-keyguard"), {
                "trigger_observation": observation, "trigger_state": state,
                "request_sent": False, "completed": False,
                "completion_scope": "requires a subsequent valid unlocked observation for the same user; exit 0 is not completion"})
            dismissal = metadata["keyguard_dismissal"]
            dismissal["request_sent"] = result.returncode == 0
            if result.returncode:
                raise RuntimeError(f"HOME keyguard dismissal failed ({result.returncode})")
            remaining()

        try:
            if self.snapshot_apk is not None:
                if self.snapshot_session is None:
                    self.snapshot_session = UiSnapshotSession(self.adb_command, self.output,
                        child_prefetch_mode=self.snapshot_child_prefetch, expected_api_level=self.api_level)
                remaining()
                metadata["session_begin"] = {"started_monotonic_seconds": time.monotonic(),
                                             "deadline_monotonic_seconds": deadline,
                                             "scope": "owned connection/readers only; ready and first root request follow initial window checks"}
                try:
                    self.snapshot_session.begin(deadline)
                finally:
                    metadata["session_begin"]["finished_monotonic_seconds"] = time.monotonic()
                remaining()
            resolve_started = time.monotonic()
            resolved = self.text("shell", "cmd", "package", "resolve-activity", "--brief",
                                 "-a", "android.intent.action.MAIN", "-c", "android.intent.category.HOME",
                                 timeout=remaining())
            metadata["home_resolve_seconds"] = round(time.monotonic() - resolve_started, 6)
            (self.output / f"{name}-baseline-home.txt").write_text(resolved, encoding="utf-8")
            components = re.findall(r"^([\w.$]+/[\w.$]+)$", resolved, re.MULTILINE)
            if len(components) != 1 or components[0].startswith("android/"):
                raise RuntimeError("Actual HOME activity did not resolve to one Launcher component")
            home = canonical_component(components[0])
            metadata["home_component"] = home
            if self.api_level is None:
                sdk_started = time.monotonic()
                self.api_level = int(self.text("shell", "getprop", "ro.build.version.sdk", timeout=remaining()).strip())
                metadata["sdk_read_seconds"] = round(time.monotonic() - sdk_started, 6)
            if self.snapshot_apk is None:
                raise RuntimeError("Real Launcher baseline requires the independent visible hierarchy reader")
            # Reuse this one public test connection for subsequent App reads;
            # the uiautomator CLI must not compete with the baseline session.
            self.hierarchy_backend = "ui-automation-snapshot"
            metadata["hierarchy_backend"] = self.hierarchy_backend
            metadata["hierarchy_backend_reason"] = "Live visible Launcher content within the shared baseline deadline"
            initial = bounded_command("initial_window_state", ("exec-out", "sh", "-c", state_command), {
                "observation_scope": "baseline entry after existing cold setup; before the first helper request; not before setup dismissal"})
            if initial.returncode:
                raise RuntimeError(f"HOME initial window state probe failed ({initial.returncode})")
            initial_state = home_window_state(initial.stdout.decode("utf-8", "replace"))
            metadata["initial_window_state"]["state"] = initial_state
            remaining()
            observe_keyguard(initial_state, "initial_window_state")
            remaining()
            while True:
                remaining()
                index = len(metadata["samples"])
                window_file = f"{name}-baseline-{index:02d}-window.txt"
                png_file = f"{name}-baseline-{index:02d}.png"
                raw_file = f"{name}-baseline-{index:02d}-batch.bin"
                frame_file = f"{name}-baseline-{index:02d}-screencap.raw"
                compressed_file = f"{name}-baseline-{index:02d}-screencap.raw.gz"
                stderr_file = f"{name}-baseline-{index:02d}-stderr.txt"
                pending_sample = {"window": window_file, "screenshot": png_file,
                                  "batch_raw": raw_file, "screencap_raw": frame_file, "stderr": stderr_file,
                                  "screencap_gzip": compressed_file, "stage": "hierarchy"}
                # Start/read the one owned connection inside this same deadline,
                # before the screenshot transfer consumes the remaining time.
                # Every sample gets a fresh matching request and XML.
                hierarchy_started = time.monotonic()
                self.hierarchy_attempts += 1
                pending_sample["hierarchy"] = f"hierarchy-{self.hierarchy_attempts:04d}.xml"
                pending_sample["hierarchy_metadata"] = f"hierarchy-snapshot-{self.hierarchy_attempts:04d}.json"
                root = self.snapshot_hierarchy(deadline=deadline)
                pending_sample["hierarchy_seconds"] = round(time.monotonic() - hierarchy_started, 6)
                launcher_content = home_launcher_content(root, home)
                remaining()
                # One fixed remote command avoids separate adb connections and
                # unrelated full-window dump sections within the same 10s budget.
                batch_started = time.monotonic()
                pending_sample["stage"] = "capture"
                pending_sample["capture_started_elapsed_seconds"] = round(batch_started - started, 6)
                pending_sample["capture_timeout_seconds"] = remaining()
                batch = self.adb("exec-out", "sh", "-c", command,
                                 timeout=pending_sample["capture_timeout_seconds"], check=False)
                batch_finished = time.monotonic()
                pending_sample["capture_seconds"] = round(batch_finished - batch_started, 6)
                pending_sample["window_state_started_monotonic_seconds"] = batch_started
                pending_sample["window_state_ended_monotonic_seconds"] = batch_finished
                pending_sample["stage"] = "raw-persistence"
                persistence_started = time.monotonic()
                (self.output / raw_file).write_bytes(batch.stdout)
                (self.output / stderr_file).write_bytes(batch.stderr)
                pending_sample["returncode"] = batch.returncode
                pending_sample["batch_bytes"] = len(batch.stdout)
                if batch.returncode:
                    if batch.stdout.count(separator) == 1:
                        failed_window, failed_gzip = batch.stdout.split(separator)
                        (self.output / window_file).write_bytes(failed_window)
                        (self.output / compressed_file).write_bytes(failed_gzip)
                    raise RuntimeError(f"HOME baseline batch failed ({batch.returncode}): {batch.stderr.decode('utf-8', 'replace')}")
                if batch.stdout.count(separator) != 1:
                    raise RuntimeError("HOME baseline batch has missing or ambiguous raw frame separator")
                window_bytes, compressed = batch.stdout.split(separator)
                (self.output / window_file).write_bytes(window_bytes)
                (self.output / compressed_file).write_bytes(compressed)
                pending_sample["gzip_bytes"] = len(compressed)
                pending_sample["gzip_sha256"] = hashlib.sha256(compressed).hexdigest()
                raw_write_seconds = time.monotonic() - persistence_started
                pending_sample["stage"] = "gzip-decode"
                gzip_started = time.monotonic()
                raw = decompress_screencap_gzip(compressed)
                gzip_finished = time.monotonic()
                pending_sample["gzip_decode_seconds"] = round(gzip_finished - gzip_started, 6)
                (self.output / frame_file).write_bytes(raw)
                pending_sample["raw_persistence_seconds"] = round(
                    raw_write_seconds + time.monotonic() - gzip_finished, 6)
                window = window_bytes.decode("utf-8", "replace")
                state = home_window_state(window)
                focused = state["focused_component"]
                pending_sample["window_state"] = state
                pending_sample["window_state_scope"] = "this sample batch only; not the initial observation or the full root-wait interval"
                decode_started = time.monotonic()
                pending_sample["stage"] = "raw-decode"
                captured, raw_metadata = decode_raw_screencap(raw, self.api_level)
                pending_sample["raw_frame"] = raw_metadata
                pending_sample["raw_decode_seconds"] = round(time.monotonic() - decode_started, 6)
                with captured:
                    # Preserve the exact full frame even when HOME geometry or
                    # readiness fails; encoding remains inside the same 10s.
                    png_started = time.monotonic()
                    pending_sample["stage"] = "png-encode"
                    encoded = io.BytesIO()
                    captured.save(encoded, format="PNG", compress_level=1)
                    png = encoded.getvalue()
                    pending_sample["png_encode_seconds"] = round(time.monotonic() - png_started, 6)
                    (self.output / png_file).write_bytes(png)
                    pending_sample["png_bytes"] = len(png)
                    pending_sample["png_sha256"] = hashlib.sha256(png).hexdigest()
                    remaining()
                    pending_sample["stage"] = "content-bounds"
                    compare_started = time.monotonic()
                    rect = home_content_bounds(window, captured.size)
                    pixels = captured.crop(rect).tobytes()
                    signature = (captured.size, rect, pixels)
                    pending_sample["decode_compare_seconds"] = round(
                        pending_sample["raw_decode_seconds"] + time.monotonic() - compare_started, 6)
                remaining()
                pending_sample["stage"] = "stability-verification"
                observe_keyguard(state, f"sample-{index:02d}")
                remaining()
                dismissal = metadata.get("keyguard_dismissal")
                keyguard_ready = state["keyguard_state"] != "locked" and \
                    (dismissal is None or dismissal.get("completed", False))
                ready = state["focus_valid"] and focused == home and bool(launcher_content) and keyguard_ready
                stable = stable + 1 if ready and signature == previous else int(ready)
                previous = signature if ready else None
                metadata["samples"].append({**pending_sample,
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "focused_component": focused, "launcher_content": launcher_content,
                    "content_bounds": list(rect), "content_sha256": hashlib.sha256(pixels).hexdigest(),
                    "stable_captures": stable})
                remaining()
                if stable >= 3:
                    metadata["passed"] = True
                    return png
                time.sleep(min(.4, remaining()))
        except Exception as error:
            metadata.update(passed=False, error=str(error))
            if pending_sample is not None:
                metadata["failed_sample"] = pending_sample
                cause = error.__cause__
                if pending_sample["stage"] == "hierarchy":
                    pending_sample["hierarchy_seconds"] = round(time.monotonic() - hierarchy_started, 6)
                if isinstance(cause, subprocess.TimeoutExpired) and \
                        "capture_started_elapsed_seconds" in pending_sample and "returncode" not in pending_sample:
                    pending_sample["capture_seconds"] = round(time.monotonic() - batch_started, 6)
                    if isinstance(cause.stdout, bytes):
                        (self.output / pending_sample["batch_raw"]).write_bytes(cause.stdout)
                        if cause.stdout.count(separator) == 1:
                            partial_window, partial_frame = cause.stdout.split(separator)
                            (self.output / pending_sample["window"]).write_bytes(partial_window)
                            (self.output / pending_sample["screencap_gzip"]).write_bytes(partial_frame)
                    if isinstance(cause.stderr, bytes):
                        (self.output / pending_sample["stderr"]).write_bytes(cause.stderr)
                pending_sample["failed_elapsed_seconds"] = round(time.monotonic() - started, 6)
            raise RuntimeError(f"{name}: HOME baseline failed: {error}") from error
        finally:
            metadata["elapsed_seconds"] = round(time.monotonic() - started, 3)
            (self.output / f"{name}-baseline-readiness.json").write_text(
                json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def begin_launch_recording(self, name: str = "cold-start"):
        """Record a bounded real launch concurrently; evidence failure is not App failure."""
        try:
            self.adb("shell", "rm", "-f", f"/sdcard/luoshu-{name}.mp4", check=False)
            process = subprocess.Popen(self.adb_command + ["shell", "screenrecord", "--time-limit", "30",
                "--bit-rate", "2000000", "--size", "720x1560", f"/sdcard/luoshu-{name}.mp4"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            time.sleep(.2)
            return process
        except (OSError, RuntimeError) as error:
            self.recordings.append({"recording": name, "available": False, "error": str(error)})
            return None

    def finish_launch_recording(self, process, name: str = "cold-start") -> None:
        evidence = {"recording": name, "available": False, "time_limit_seconds": 30,
                    "scope": "raw device screenrecord; no guaranteed artwork frame; App timing and animations unchanged"}
        try:
            stdout, stderr = process.communicate(timeout=35)
            (self.output / f"{name}-recording.txt").write_bytes(stdout + stderr)
            evidence["returncode"] = process.returncode
            if process.returncode:
                raise RuntimeError((stdout + stderr).decode("utf-8", "replace"))
            video = self.output / f"{name}.mp4"
            pulled = self.adb("pull", f"/sdcard/luoshu-{name}.mp4", str(video), check=False, timeout=30)
            if pulled.returncode or not video.is_file() or b"ftyp" not in video.read_bytes()[:64]:
                raise RuntimeError("Device launch recording was not returned as a valid MP4")
            evidence.update(available=True, file=video.name, bytes=video.stat().st_size)
        except (OSError, RuntimeError, subprocess.TimeoutExpired) as error:
            if process.poll() is None:
                try:
                    process.kill()  # Only this host adb reader; device recorder has its own 30s limit.
                    process.communicate(timeout=3)
                except (OSError, subprocess.TimeoutExpired) as cleanup_error:
                    evidence["cleanup_error"] = str(cleanup_error)
            evidence["error"] = str(error)
        finally:
            self.recordings.append(evidence)

    def launch_and_capture(self, name: str) -> ET.Element:
        start = time.monotonic()
        launch = self.text("shell", "am", "start", "-W", "-n", f"{self.package}/io.github.xgl34222220.luoshu.MainActivity", timeout=45)
        am_finished = time.monotonic()
        (self.output / f"{name}-launch.txt").write_text(launch, encoding="utf-8")
        if "Status: ok" not in launch or "Error:" in launch:
            raise RuntimeError(f"MainActivity launch failed: {launch}")
        page_started = time.monotonic()
        root = self.wait_page("首页", "当前字体")
        page_finished = time.monotonic()
        self.capture(f"{name}-home", root)
        capture_finished = time.monotonic()
        # Keep this launch's events before later system traffic replaces the
        # main log buffer; normal crash checks continue to read every buffer.
        startup_log = self.logcat(f"{name}-startup-logcat.txt")
        pid = self.text("shell", "pidof", self.package).strip().split()[0]
        events = [] if "warm" in name else assert_single_stage_startup(startup_log, pid, self.api_level or 28)
        window = self.text("shell", "dumpsys", "window")
        (self.output / f"{name}-startup-window.txt").write_text(window, encoding="utf-8")
        evidence_finished = time.monotonic()
        self.record(f"{name}-startup-content-delivery", events=events, pid=pid,
                    system_displayed=bool(re.search(rf"Displayed\s+{re.escape(self.package)}/", startup_log)),
                    scope="Current App PID content events and real window/system logs; visual acceptance is separate")
        self.record(name, ui_ready_seconds=round(time.monotonic() - start, 3),
                    ui_ready_seconds_scope="Host am command, page wait, screenshot and startup evidence collection through record",
                    am_command_seconds=round(am_finished - start, 3),
                    page_wait_seconds=round(page_finished - page_started, 3),
                    home_capture_seconds=round(capture_finished - page_finished, 3),
                    startup_evidence_seconds=round(evidence_finished - capture_finished, 3),
                    am_total_time_ms=re.search(r"TotalTime:\s*(\d+)", launch).group(1) if re.search(r"TotalTime:\s*(\d+)", launch) else None)
        return root

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

    def verify_rapid_navigation(self) -> None:
        root = self.ensure_dock()
        coordinates = {label: center(tab_target(root, label, self.package)) for _, label, _ in PAGES}
        sequence = ("首页", "组合", "字体库", "设置", "字体库", "首页", "设置", "组合", "首页")
        for label in sequence:
            x, y = coordinates[label]
            self.adb("shell", "input", "tap", str(x), str(y))
        root = self.wait_page("首页", "当前字体")
        self.capture("rapid-navigation-home", root)
        self.record("rapid-navigation", taps=list(sequence), final_tab="首页")

    def verify_settings_details(self) -> None:
        self.select_tab("设置", "你的洛书")
        self.tap_label("外观与主题", scroll_attempts=8)
        root = self.wait_ui(
            lambda root: {"外观与主题", "外观预览", "颜色与模式"}.issubset(app_labels(root, self.package)),
            "Appearance settings detail",
        )
        try:
            tab_target(root, "设置", self.package)
        except ValueError:
            pass
        else:
            raise RuntimeError("Bottom navigation remains actionable over a settings detail")
        for label, filename in (("浅色", "appearance-light"), ("深色", "appearance-dark"), ("跟随系统", "appearance-system")):
            self.tap_label(label, scroll_attempts=5)
            root = self.wait_ui(lambda root: choice_selected(root, label, self.package), f"Selected theme {label!r}")
            self.capture(filename, root)
            self.record(filename, selected_label=label)
        if self.api_level is not None and self.api_level < 31:
            self.verify_legacy_palette()
        self.adb("shell", "input", "keyevent", "KEYCODE_BACK")
        root = self.wait_page("设置", "你的洛书")
        self.capture("settings-detail-return", root)
        self.record("settings-detail-return", restored_tab="设置")

    def verify_legacy_palette(self) -> None:
        for _ in range(8):
            root = self.hierarchy()
            if legacy_manual_colors_ready(root, self.package):
                break
            self.scroll(root)
        else:
            raise RuntimeError("Legacy Android manual theme colors were blocked or wallpaper capability was misstated")
        for label, name in (("曜紫", "legacy-theme-purple"), ("青蓝", "legacy-theme-cyan")):
            self.tap_label(label)
            root = self.wait_ui(lambda root: choice_selected(root, label, self.package), f"Legacy manual color {label!r}")
            self.capture(name, root)
            self.record(name, selected_label=label)
        for _ in range(8):
            root = self.hierarchy()
            if legacy_monet_unavailable(root, self.package):
                self.capture("legacy-monet-unavailable", root)
                self.record("legacy-monet-capability", wallpaper_supported=False, manual_colors_enabled=True)
                return
            self.scroll(root)
        raise RuntimeError("Unsupported legacy Monet option was not disabled with its Android 12 requirement")

    def verify_library_empty_management_reveal(self) -> None:
        # Use the production empty state at the same real smaller viewport as
        # preservation. Only the pre-tap search may scroll to the empty entry.
        self.adb("shell", "wm", "size", "1080x1920")
        self.adb("shell", "wm", "density", "420")
        self.select_tab("字体库", "搜索你的字体")
        root = self.wait_ui(
            lambda current: page_ready(current, "字体库", "搜索你的字体", self.package)
                and choice_selected(current, "全部", self.package)
                and visible_control(current, "搜索你的字体", self.package) is not None
                and visible_action(current, "全部", self.package) is not None
                and "导入与管理" in app_labels(current, self.package),
            "Unfiltered empty library before its management entry",
        )
        root = self.reach_content(
            lambda current: visible_action(current, "打开导入与管理", self.package) is not None
                and visible_control(current, "打开导入与管理", self.package) is not None,
            "Whole production empty-library management entry", root=root,
            budget=ScrollBudget(timeout=90, max_gestures=5),
        )
        target = visible_action(root, "打开导入与管理", self.package)
        self.capture("library-empty-management-before-tap", root)
        x, y = center(target)
        self.adb("shell", "input", "tap", str(x), str(y))
        last_root = root

        def revealed(current: ET.Element) -> bool:
            nonlocal last_root
            last_root = current
            return (page_ready(current, "字体库", "收起管理", self.package)
                    and visible_action(current, "收起管理", self.package) is not None
                    and visible_control(current, "收起管理", self.package) is not None
                    and visible_control(current, "导入字体", self.package) is not None)

        try:
            # Never help the UI with a post-tap gesture: this is the reveal test.
            root = self.wait_ui(revealed, "Empty-library entry reveals whole import tools without a test scroll")
        except Exception as error:
            try:
                self.capture("library-empty-management-after-tap", last_root)
            except Exception as capture_error:
                raise RuntimeError(f"{error}; reveal failure capture also failed: {capture_error}") from error
            raise
        self.capture("library-empty-management-after-tap", root)
        self.record("library-empty-management-reveal", entry="打开导入与管理", revealed="导入字体",
                    import_enabled=visible_control(root, "导入字体", self.package).get("enabled"),
                    selected_tab="字体库", post_tap_test_scrolls=0, viewport="1080x1920@420dpi")
        x, y = center(visible_action(root, "收起管理", self.package))
        self.adb("shell", "input", "tap", str(x), str(y))
        root = self.wait_ui(
            lambda current: "导入与管理" in app_labels(current, self.package)
                and "收起管理" not in app_labels(current, self.package),
            "Management tools closed after the empty-entry reveal",
        )
        root = self.reach_content(
            lambda current: page_ready(current, "字体库", "搜索你的字体", self.package)
                and choice_selected(current, "全部", self.package)
                and visible_control(current, "搜索你的字体", self.package) is not None
                and visible_action(current, "全部", self.package) is not None,
            "Unfiltered library search restored before preservation", direction="down", root=root,
            budget=ScrollBudget(timeout=90, max_gestures=8),
        )
        self.capture("library-empty-management-restored-top", root)

    def verify_library_preservation(self) -> None:
        # A real smaller emulator viewport makes an empty library scrollable.
        # It still uses production data and controls; no mock fonts are inserted.
        self.adb("shell", "wm", "size", "1080x1920")
        self.adb("shell", "wm", "density", "420")
        self.select_tab("字体库", "搜索你的字体")
        self.tap_label("收藏", scroll_attempts=8)
        root = self.wait_ui(lambda root: choice_selected(root, "收藏", self.package), "Favorite library filter")
        self.capture("library-favorite-filter", root)
        self.tap_label("导入与管理", scroll_attempts=5)
        root = self.wait_ui(lambda root: "收起管理" in app_labels(root, self.package), "Expanded production font management tools")
        initial = visible_scroll_anchors(root, self.package)
        self.capture("library-management-expanded-before-scroll", root)
        # Reach the production empty-library action below the real management
        # rows. A gesture count or a disappearing dock is never scroll proof.
        root = self.reach_content(lambda current: visible_action(current, "清除筛选", self.package),
            "Font library real scroll below expanded management rows", root=root,
            budget=ScrollBudget(timeout=90, max_gestures=5))
        if not scroll_progress(initial, visible_scroll_anchors(root, self.package), "up"):
            raise RuntimeError("Font library did not produce an observable real scroll in the smaller viewport")
        root = self.ensure_dock()
        scrolled = content_anchors(root, self.package)
        if not scrolled or anchors_preserved(initial, scrolled):
            raise RuntimeError("Quick Return did not leave a measurable library scroll to verify")
        self.capture("library-scrolled-before-tab", root)
        self.select_tab("设置")
        self.select_tab("组合")
        self.select_tab("字体库")
        root = self.wait_ui(
            lambda root: anchors_preserved(scrolled, content_anchors(root, self.package)),
            "Font library scroll position after leaving and returning to its tab",
        )
        self.capture("library-scrolled-after-tab", root)
        self.record("library-scroll-across-tabs", anchors=scrolled, viewport="1080x1920@420dpi",
                    library_data="production App data on the unrooted emulator; no imported font fixture")
        # Restore the top to inspect selected semantics rather than inferring the
        # filter from a screenshot color or from an unselected label still present.
        root = self.reach_content(lambda current: visible_action(current, "收藏", self.package),
            "Favorite filter after changing tabs", direction="down", root=root,
            budget=ScrollBudget(timeout=90, max_gestures=8))
        if not choice_selected(root, "收藏", self.package):
            raise RuntimeError("Favorite filter selection was not preserved after changing tabs")
        self.capture("library-filter-after-tab", root)
        self.record("library-filter-across-tabs", selected_label="收藏")
        background_anchors = content_anchors(root, self.package)
        self.adb("shell", "input", "keyevent", "KEYCODE_HOME")
        time.sleep(.5)
        self.adb("shell", "am", "start", "-W", "-n", f"{self.package}/io.github.xgl34222220.luoshu.MainActivity", timeout=45)
        root = self.wait_ui(
            lambda root: library_state_preserved(root, background_anchors, self.package),
            "Library page, filter and scroll position on returning from the background",
        )
        self.capture("library-background-preserved", root)
        self.record("library-background-preserved", selected_label="收藏", anchors=background_anchors)
        # Verify the saved state before scrolling: the search field can be above
        # the viewport. Then reach it by a real gesture and keep the original
        # selected-page, search-content and selected-filter assertions intact.
        # This separate return phase retains its own original eight-gesture cap;
        # HOME/am waits do not consume either restoration search's time budget.
        root = self.reach_content(
            lambda current: page_ready(current, "字体库", "搜索你的字体", self.package)
                and choice_selected(current, "收藏", self.package)
                and visible_text(current, "搜索你的字体", self.package)
                and visible_action(current, "收藏", self.package),
            "Library search and preserved favorite filter after background return",
            direction="down", root=root, budget=ScrollBudget(timeout=90, max_gestures=8))
        if not (page_ready(root, "字体库", "搜索你的字体", self.package)
                and choice_selected(root, "收藏", self.package)):
            raise RuntimeError("Font library search and preserved favorite filter were not reachable after background return")
        self.capture("library-background-return", root)
        self.record("library-background-return", selected_label="收藏")

        rotation_preferences = {key: self.text("shell", "settings", "get", "system", key).strip()
                                for key in ("accelerometer_rotation", "user_rotation")}
        try:
            self.adb("shell", "settings", "put", "system", "accelerometer_rotation", "0")
            self.adb("shell", "settings", "put", "system", "user_rotation", "1")
            root = self.wait_ui(
                lambda root: orientation_matches(root, self.package, landscape=True),
                "Actual landscape configuration",
            )
            root = self.find_choice("收藏")
            self.capture("library-landscape", root)
            self.logcat("landscape-startup-logcat.txt")
            self.adb("shell", "settings", "put", "system", "user_rotation", "0")
            root = self.wait_ui(
                lambda root: orientation_matches(root, self.package, landscape=False),
                "Actual portrait configuration",
            )
            # Reach the real filter from the rotated scroll position. A fixed
            # number of swipes cannot establish that the selected row is visible.
            root = self.find_choice("收藏", direction="down")
            self.capture("library-portrait-return", root)
            self.logcat("portrait-return-startup-logcat.txt")
            self.record("library-rotation-return", selected_label="收藏", rotations=["landscape", "portrait"])
        finally:
            for key, value in rotation_preferences.items():
                if value == "null":
                    self.adb("shell", "settings", "delete", "system", key)
                else:
                    self.adb("shell", "settings", "put", "system", key, value)
            self.adb("shell", "wm", "size", "reset")
            self.adb("shell", "wm", "density", "reset")

    def verify_disabled_animations(self) -> None:
        keys = ("animator_duration_scale", "transition_animation_scale", "window_animation_scale")
        previous = {key: self.text("shell", "settings", "get", "global", key).strip() for key in keys}
        try:
            for key in keys:
                self.adb("shell", "settings", "put", "global", key, "0")
                applied = self.text("shell", "settings", "get", "global", key).strip()
                if float(applied) != 0:
                    raise RuntimeError(f"System animation scale {key} was not disabled: {applied}")
            self.verify_rapid_navigation()
            self.select_tab("设置", "你的洛书")
            self.tap_label("外观与主题", scroll_attempts=8)
            root = self.wait_ui(lambda root: "外观预览" in app_labels(root, self.package), "Appearance detail with system animations disabled")
            self.capture("animations-disabled-appearance", root)
            self.adb("shell", "input", "keyevent", "KEYCODE_BACK")
            root = self.wait_page("设置", "你的洛书")
            self.capture("animations-disabled-settings-return", root)
            self.logcat("animations-disabled-startup-logcat.txt")
            self.record("system-animations-disabled", scales={key: 0 for key in keys})
        finally:
            for key, value in previous.items():
                if value == "null":
                    self.adb("shell", "settings", "delete", "global", key)
                else:
                    self.adb("shell", "settings", "put", "global", key, value)

    def run(self) -> None:
        self.adb("wait-for-device", timeout=60)
        self.adb("install", "-r", "-g", str(self.apk), timeout=120)
        if self.snapshot_apk is not None:
            self.adb("install", "-r", str(self.snapshot_apk), timeout=120)
        self.adb("shell", "pm", "clear", self.package)
        # Clearing App data also revokes the grant made by install -g. Grant this
        # permission after the reset so the first-run dialog cannot cover the UI.
        self.api_level = int(self.text("shell", "getprop", "ro.build.version.sdk").strip())
        if self.api_level >= 33:
            self.adb("shell", "pm", "grant", self.package, "android.permission.POST_NOTIFICATIONS")
        self.adb("logcat", "-c")
        self.adb("shell", "input", "keyevent", "KEYCODE_WAKEUP")
        self.adb("shell", "wm", "dismiss-keyguard")
        self.adb("shell", "cmd", "uimode", "night", "no")
        if self.visual_launch_only:
            errors = []
            for theme, mode in (("light", "no"), ("dark", "yes")):
                self.adb("shell", "cmd", "uimode", "night", mode)
                self.adb("shell", "input", "keyevent", "KEYCODE_HOME")
                self.adb("shell", "am", "force-stop", self.package)
                for kind in ("cold", "warm"):
                    name = f"{theme}-{kind}-start"
                    previous_pid = None
                    if kind == "warm":
                        try:
                            previous_pid = self.text("shell", "pidof", self.package, check=False).strip()
                        except RuntimeError as error:
                            errors.append(f"{name}: cannot establish existing App PID; warm recording skipped: {error}")
                            continue
                        if re.fullmatch(r"[1-9]\d*", previous_pid) is None:
                            errors.append(f"{name}: warm launch requires one existing App PID; pidof returned {previous_pid!r}; warm recording skipped")
                            continue
                        self.adb("shell", "input", "keyevent", "KEYCODE_HOME")
                    self.adb("logcat", "-c")
                    try:
                        self.launch(name)
                    except RuntimeError as error:
                        errors.append(f"{name}: {error}")
                    if kind == "warm":
                        try:
                            current_pid = self.text("shell", "pidof", self.package, check=False).strip()
                        except RuntimeError as error:
                            errors.append(f"{name}: cannot verify resumed App PID: {error}")
                            continue
                        if current_pid != previous_pid:
                            errors.append(f"{name}: warm resume changed App PID {previous_pid} to {current_pid}")
                        else:
                            self.record(f"{name}-same-process", before_pid=previous_pid, after_pid=current_pid)
            if errors:
                raise RuntimeError("; ".join(errors))
            self.assert_running()
            return
        self.launch("cold-start")
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
                if theme == "light" and name == "home":
                    root = self.wait_ui(
                        lambda root: page_ready(root, label, marker, self.package)
                        and "未连接" in app_labels(root, self.package)
                        and bool({"等待模块", "需要授权"} & app_labels(root, self.package))
                        and not {"检测中…", "核实中…", "正在连接"} & app_labels(root, self.package)
                        and any("Root" in value and "权限" in value for value in app_labels(root, self.package)),
                        "Completed unavailable Root/module check on the real emulator home",
                    )
                    self.record("unavailable-home-settled", version="未连接", connection_state="Root/module unavailable")
                if theme == "light" and name == "library":
                    root = self.wait_ui(
                        lambda root: page_ready(root, label, marker, self.package)
                        and "正在处理字体，请稍候…" not in app_labels(root, self.package)
                        and any("Root" in value and "权限" in value for value in app_labels(root, self.package))
                        and action_disabled(root, "刷新字体库", self.package),
                        "Unavailable Root library reports its error and blocked action without pretending work is running",
                    )
                    self.record("unavailable-library-settled", blocked_action="刷新字体库", error_visible=True,
                                false_operation_progress=False)
                # Keep the production animations enabled; capture once navigation settles.
                time.sleep(0.7)
                self.capture(f"{theme}-{name}", root)
                if theme == "light" and name == "home":
                    self.logcat("cold-start-settled-startup-logcat.txt")
        # Exercise STOPPED -> STARTED without stopping the process or masking crashes.
        self.adb("shell", "input", "keyevent", "KEYCODE_HOME")
        time.sleep(1)
        self.adb("shell", "am", "start", "-W", "-n", f"{self.package}/io.github.xgl34222220.luoshu.MainActivity", timeout=45)
        root = self.wait_page("设置", "你的洛书")
        self.capture("dark-settings-resumed", root)
        self.record("settings-background-return", restored_tab="设置")
        self.verify_rapid_navigation()
        self.verify_settings_details()
        self.verify_library_empty_management_reveal()
        self.verify_library_preservation()
        self.verify_disabled_animations()
        self.select_tab("首页", "当前字体")
        self.adb("shell", "am", "force-stop", self.package)
        self.launch("repeat-cold-start")
        self.select_tab("设置", "你的洛书")
        if self.api_level is not None and self.api_level < 31:
            self.tap_label("外观与主题", scroll_attempts=8)
            root = self.find_choice("青蓝")
            self.capture("legacy-theme-after-cold-start", root)
            self.record("legacy-theme-persistence", selected_label="青蓝", app_restart="force-stop and cold start")
            self.adb("shell", "input", "keyevent", "KEYCODE_BACK")
            self.wait_page("设置", "你的洛书")
        self.assert_running()

    def diagnostics(self) -> None:
        for filename, arguments in (
            ("logcat.txt", ("logcat", "-b", "all", "-d", "-v", "threadtime")),
            ("activity.txt", ("shell", "dumpsys", "activity", "activities")),
            ("last-anr.txt", ("shell", "dumpsys", "activity", "lastanr")),
            ("anr-traces.txt", ("shell", "dumpsys", "activity", "lastanr-traces")),
            ("window.txt", ("shell", "dumpsys", "window")),
            ("dropbox-anr.txt", ("shell", "dumpsys", "dropbox", "--print", "data_app_anr")),
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
    parser.add_argument("--snapshot-apk", type=Path,
                        help="Independent UiAutomation test APK for reading live hierarchy when the platform dump cannot reach global idle")
    parser.add_argument("--record-launch", action="store_true",
                        help="Optional raw cold-start video evidence; disabled by default to keep encoding load out of UI validation")
    parser.add_argument("--visual-launch-only", action="store_true",
                        help="Require every-frame light/dark cold and same-process warm launch evidence, separately from functional UI regression")
    parser.add_argument("--snapshot-child-prefetch", choices=("zero", "default"), default="zero",
                        help="Public child getter strategy; default is an explicit visual compatibility experiment")
    args = parser.parse_args()
    if args.visual_launch_only and not args.record_launch:
        parser.error("--visual-launch-only requires --record-launch")
    if args.snapshot_child_prefetch == "default" and (not args.visual_launch_only or args.snapshot_apk is None):
        parser.error("--snapshot-child-prefetch default requires --visual-launch-only and --snapshot-apk")
    if not args.apk.is_file():
        parser.error(f"APK does not exist: {args.apk}")
    if args.snapshot_apk is not None and not args.snapshot_apk.is_file():
        parser.error(f"Snapshot test APK does not exist: {args.snapshot_apk}")
    if not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+", args.package):
        parser.error("Invalid Android package name")
    run = SmokeRun(args.apk.resolve(), args.output.resolve(), args.package, args.serial,
                   args.snapshot_apk.resolve() if args.snapshot_apk is not None else None,
                   record_launch=args.record_launch, visual_launch_only=args.visual_launch_only,
                   snapshot_child_prefetch=args.snapshot_child_prefetch)
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
        try:
            run.diagnostics()
        except Exception as failure:
            diagnostic_error = f"diagnostics {type(failure).__name__}: {failure}"
            print(diagnostic_error, file=sys.stderr, flush=True)
            error = f"{error}; {diagnostic_error}" if error else diagnostic_error
        finally:
            try:
                run.close_snapshot_session()
            except Exception as failure:
                cleanup_error = f"{type(failure).__name__}: {failure}"
                print(cleanup_error, file=sys.stderr, flush=True)
                error = f"{error}; {cleanup_error}" if error else cleanup_error
        final_log = run.output / "logcat.txt"
        if final_log.is_file():
            final_crash = crash_reason(final_log.read_text(encoding="utf-8", errors="replace"), args.package)
            if final_crash and (error is None or final_crash not in error):
                error = f"{error}; {final_crash}" if error else final_crash
        if run.adb_diagnostic_errors:
            diagnostic_error = "; ".join(run.adb_diagnostic_errors)
            error = f"{error}; {diagnostic_error}" if error else diagnostic_error
        summary = {"passed": error is None, "error": error, "seconds": round(time.monotonic() - run.started_at, 2),
                   "mode": "visual-launch-only" if run.visual_launch_only else "functional-ui-smoke",
                   "api_level": run.api_level, "scope": "unrooted emulator UI; no real-device font replacement validation",
                   "snapshot_child_prefetch": run.snapshot_child_prefetch,
                   "hierarchy_backend": run.hierarchy_backend,
                   "adb_command_count": run.adb_command_count,
                   "adb_diagnostic_errors": run.adb_diagnostic_errors,
                   "launch_recording_enabled": run.record_launch,
                   "screens": run.results, "checks": run.checks, "recordings": run.recordings}
        (run.output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if error is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
