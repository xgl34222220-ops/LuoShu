#!/usr/bin/env python3
"""Inspect every decoded launch frame against real artwork and semantic home crops.

No sampled fps, event-name absence, or screenshot background color is proof of a
single handoff. Unknown frames remain explicit failures. References are real CI
native-logo crops; home references come from this run's real screenshot and XML.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.signal import correlate


MATCH_WIDTH = 360
LOGO_MATCH = .92
HOME_MATCH = .92
TRANSITION_MATCH = .72


def edges(rgb: np.ndarray) -> np.ndarray:
    gray = rgb.astype(np.float32).mean(axis=2)
    dx = np.diff(gray, axis=1, prepend=gray[:, :1])
    dy = np.diff(gray, axis=0, prepend=gray[:1, :])
    return np.hypot(dx, dy)


def match_score(area: np.ndarray, template: np.ndarray) -> float:
    """Normalized correlation of actual ink edges, excluding flat backgrounds."""
    height, width = template.shape
    if area.shape[0] < height or area.shape[1] < width or template.std() < 1:
        return 0.0
    centered = template - template.mean()
    numerator = correlate(area, centered, mode="valid", method="fft")
    integral = np.pad(area.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    squared = np.pad((area * area).cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    def totals(table):
        return table[height:, width:] - table[:-height, width:] - table[height:, :-width] + table[:-height, :-width]
    variance = np.maximum(totals(squared) - totals(integral) ** 2 / template.size, 0)
    denominator = np.sqrt(variance * (centered * centered).sum())
    scores = np.divide(numerator, denominator, out=np.zeros_like(numerator), where=denominator > 1)
    return float(np.clip(scores.max(), 0, 1))


def resized(image: Image.Image, size: tuple[int, int]) -> np.ndarray:
    return np.asarray(image.convert("RGB").resize(size, Image.Resampling.LANCZOS))


class FrameClassifier:
    def __init__(self, home: Image.Image, hierarchy: ET.Element, theme: str,
                 size: tuple[int, int], baseline: Image.Image | None = None):
        self.size = size
        self.reference = resized(home, size)
        self.home_patches = []
        reference_edges = edges(self.reference)
        # Two independent real content strings survive Root-status updates.
        # A flat full-frame similarity could wrongly accept the opaque splash.
        for label in ("当前字体", "系统默认字体"):
            nodes = [node for node in hierarchy.iter("node") if node.get("text") == label]
            if len(nodes) != 1:
                raise RuntimeError(f"Home screenshot needs one real semantic reference for {label!r}")
            import re
            rect = tuple(map(int, re.findall(r"\d+", nodes[0].get("bounds", ""))))
            if len(rect) != 4:
                raise RuntimeError(f"Home reference has invalid bounds for {label!r}")
            x1, y1, x2, y2 = (round(value * size[index % 2] / home.size[index % 2]) for index, value in enumerate(rect))
            template = reference_edges[max(0, y1 - 2):y2 + 2, max(0, x1 - 2):x2 + 2]
            if template.std() < 1:
                raise RuntimeError(f"Home reference crop for {label!r} has no visible text")
            self.home_patches.append((label, (max(0, x1 - 6), max(0, y1 - 70), min(size[0], x2 + 6), min(size[1], y2 + 70)), template))
        fixtures = Path(__file__).with_name("startup_visual_fixtures")
        # Original emulator is 720x1560; normalize both fixture and real frame.
        self.logo = edges(resized(Image.open(fixtures / f"native-logo-{theme}.png"), (168, 168)))
        self.baseline = edges(resized(baseline, size)) if baseline is not None else None

    def classify(self, frame: np.ndarray) -> dict:
        height, width, _ = frame.shape
        interior = frame[int(height * .06):int(height * .94), int(width * .04):int(width * .96)]
        black_fraction = float(np.mean(interior.max(axis=2) < 8))
        edge_frame = edges(frame)
        logo_score = match_score(edge_frame[int(height * .32):int(height * .69), int(width * .20):int(width * .80)], self.logo)
        home_scores = {}
        for label, (x1, y1, x2, y2), template in self.home_patches:
            home_scores[label] = match_score(edge_frame[y1:y2, x1:x2], template)
        baseline_score = 0.0
        if self.baseline is not None:
            area = edge_frame[int(height * .06):int(height * .94)]
            template = self.baseline[int(height * .06):int(height * .94)]
            baseline_score = match_score(area, template)
        if black_fraction >= .995:
            state = "black-blank"
        elif logo_score >= LOGO_MATCH:
            state = "native-logo"
        elif min(home_scores.values()) >= HOME_MATCH:
            state = "home"
        elif logo_score >= TRANSITION_MATCH:
            state = "logo-transition"
        elif min(home_scores.values()) >= TRANSITION_MATCH:
            state = "home-transition"
        elif baseline_score >= .95:
            state = "prelaunch"
        else:
            state = "unclassified"
        return {"state": state, "logo_score": round(logo_score, 5),
                "home_scores": {key: round(value, 5) for key, value in home_scores.items()},
                "baseline_score": round(baseline_score, 5), "black_fraction": round(black_fraction, 5)}


def timeline_verdict(frames: list[dict], *, warm: bool = False) -> dict:
    errors = []
    home_seen = False
    logo_seen = False
    for frame in frames:
        state = frame["state"]
        stamp = f"frame {frame['frame']} at {frame['seconds']:.6f}s"
        if state in ("native-logo", "logo-transition"):
            if home_seen:
                errors.append(f"Native logo returned after visible home: {stamp}")
            if warm:
                errors.append(f"Warm same-process resume displayed branded startup: {stamp}")
            logo_seen = True
        if state in ("home", "home-transition"):
            home_seen = True
        if state == "black-blank":
            errors.append(f"Black blank screen: {stamp}")
        if state == "unclassified":
            errors.append(f"Unclassified visual evidence: {stamp}")
        if state == "prelaunch" and (logo_seen or home_seen):
            errors.append(f"Launch returned to the previous surface: {stamp}")
    if not home_seen:
        errors.append("Recording never established visible real home content")
    if not frames or frames[-1]["state"] != "home":
        errors.append("Recording did not finish with visible real home content")
    return {"passed": not errors, "errors": errors, "home_seen": home_seen,
            "logo_seen": logo_seen, "unclassified_frames": sum(frame["state"] == "unclassified" for frame in frames)}


def inspect_recording(video: Path, home: Path, hierarchy: Path, theme: str, output: Path,
                      *, baseline: Path | None = None, warm: bool = False) -> dict:
    info = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height:frame=best_effort_timestamp_time", "-of", "json", str(video)]))
    stream = info["streams"][0]
    size = (MATCH_WIDTH, round(stream["height"] * MATCH_WIDTH / stream["width"]))
    if abs(size[1] / size[0] - 1560 / 720) > .02:
        raise RuntimeError("Startup artwork matching requires the recorded portrait emulator aspect ratio")
    classifier = FrameClassifier(Image.open(home), ET.parse(hierarchy).getroot(), theme, size,
                                 Image.open(baseline) if baseline is not None else None)
    process = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(video), "-vsync", "0",
        "-vf", f"scale={size[0]}:{size[1]}", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    frames = []
    try:
        for index, timestamp in enumerate(info["frames"]):
            data = process.stdout.read(size[0] * size[1] * 3)
            if len(data) != size[0] * size[1] * 3:
                raise RuntimeError("Decoder omitted or truncated an original video frame")
            result = classifier.classify(np.frombuffer(data, dtype=np.uint8).reshape(size[1], size[0], 3))
            frames.append({"frame": index, "seconds": float(timestamp["best_effort_timestamp_time"]), **result})
        if process.stdout.read(1):
            raise RuntimeError("Decoded frame count differs from the original presentation timestamps")
        error = process.stderr.read().decode("utf-8", "replace")
        if process.wait(timeout=10):
            raise RuntimeError(f"Frame decoder failed: {error}")
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
    result = {"video": video.name, "sha256": hashlib.sha256(video.read_bytes()).hexdigest(),
              "scope": "Every original decoded frame and presentation timestamp; real semantic home and native artwork image matching",
              "theme": theme, "warm_same_process": warm, "frames_decoded": len(frames),
              "thresholds": {"logo": LOGO_MATCH, "home": HOME_MATCH, "recognized_transition": TRANSITION_MATCH},
              **timeline_verdict(frames, warm=warm), "frames": frames}
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for argument in ("video", "home", "hierarchy", "output"):
        parser.add_argument(f"--{argument}", type=Path, required=True)
    parser.add_argument("--theme", choices=("light", "dark"), required=True)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--warm", action="store_true")
    args = parser.parse_args()
    result = inspect_recording(args.video, args.home, args.hierarchy, args.theme, args.output,
                               baseline=args.baseline, warm=args.warm)
    for error in result["errors"]:
        print(error)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
