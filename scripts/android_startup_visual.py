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
import math
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from contextlib import ExitStack
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.signal import correlate


MATCH_WIDTH = 360
LOGO_MATCH = .92
HOME_MATCH = .92
TRANSITION_MATCH = .72
SHELL_TEXT_MATCH = .92
# Launch shell wordmark 「洛书」 and subtitle 「LuoShu · 字体管理」 below the centred glass card
# (LuoShuLaunchArtwork geometry on the 360x780 normalized frame).
SHELL_TEXT_BOUNDS = ((140, 498, 220, 540), (112, 541, 248, 563))
# The glass card (with shadow) settles and scales during the shell; its area is checked by
# neither the background comparison nor blend fits. Text crops and the field around it are.
SHELL_CARD_BOUNDS = (48, 258, 312, 524)
# Low-resolution comparison of the diffuse field: slow drift and accent glows are tolerated,
# a blank, flat, shifted or different surface is not.
FIELD_CELL = 10
FIELD_MEAN_TOLERANCE = 8.0
FIELD_CELL_TOLERANCE = 18.0
FIELD_CELL_FRACTION = .98
BLEND_MIN = .08
BLEND_MAX = .92
BLEND_MEAN_RESIDUAL = 8.0
BLEND_P98_RESIDUAL = 22.0
BLEND_IMPROVEMENT = .6
BLEND_MIN_ENDPOINT_DIFFERENCE = 10.0
SURFACE_SCALES = tuple(index / 200 for index in range(130, 211))
SURFACE_SHIFT = (20, 80)


def edges(rgb: np.ndarray) -> np.ndarray:
    gray = rgb.astype(np.float32).mean(axis=2)
    dx = np.diff(gray, axis=1, prepend=gray[:, :1])
    dy = np.diff(gray, axis=0, prepend=gray[:1, :])
    return np.hypot(dx, dy)


def match_scores(area: np.ndarray, template: np.ndarray) -> np.ndarray:
    """Normalized correlation of actual ink edges, excluding flat backgrounds."""
    height, width = template.shape
    if area.shape[0] < height or area.shape[1] < width or template.std() < 1:
        return np.empty((0, 0), dtype=np.float32)
    centered = template - template.mean()
    numerator = correlate(area, centered, mode="valid", method="fft")
    integral = np.pad(area.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    squared = np.pad((area * area).cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    def totals(table):
        return table[height:, width:] - table[:-height, width:] - table[height:, :-width] + table[:-height, :-width]
    variance = np.maximum(totals(squared) - totals(integral) ** 2 / template.size, 0)
    denominator = np.sqrt(variance * (centered * centered).sum())
    scores = np.divide(numerator, denominator, out=np.zeros_like(numerator), where=denominator > 1)
    return np.clip(scores, 0, 1)


def match_score(area: np.ndarray, template: np.ndarray) -> float:
    scores = match_scores(area, template)
    return float(scores.max()) if scores.size else 0.0


def resized(image: Image.Image, size: tuple[int, int]) -> np.ndarray:
    return np.asarray(image.convert("RGB").resize(size, Image.Resampling.LANCZOS))


def field(rgb: np.ndarray) -> np.ndarray:
    """Box-averaged low-resolution colour field (cells of FIELD_CELL pixels)."""
    height, width, _ = rgb.shape
    rows, cols = height // FIELD_CELL, width // FIELD_CELL
    cropped = rgb[:rows * FIELD_CELL, :cols * FIELD_CELL].astype(np.float32)
    return cropped.reshape(rows, FIELD_CELL, cols, FIELD_CELL, 3).mean(axis=(1, 3))


def field_mask(size: tuple[int, int], exclude: tuple[tuple[int, int, int, int], ...]) -> np.ndarray:
    """Cells inside the content area (status/navigation bars excluded) and outside exclusions."""
    width, height = size
    rows, cols = height // FIELD_CELL, width // FIELD_CELL
    mask = np.zeros((rows, cols), dtype=bool)
    mask[int(np.ceil(height * .06 / FIELD_CELL)):int(height * .94 // FIELD_CELL), :] = True
    for x1, y1, x2, y2 in exclude:
        mask[max(0, y1 // FIELD_CELL):min(rows, -(-y2 // FIELD_CELL)),
             max(0, x1 // FIELD_CELL):min(cols, -(-x2 // FIELD_CELL))] = False
    return mask


def blend_fit(frame: np.ndarray, first: np.ndarray, second: np.ndarray, mask: np.ndarray) -> dict:
    """Explain a low-res frame as (1-b)*first + b*second; report b and the residuals."""
    a, b, f = first[mask], second[mask], frame[mask]
    span = b - a
    endpoint_difference = float(np.abs(span).max(axis=1).mean())
    denominator = float((span * span).sum())
    weight = float(np.clip(((f - a) * span).sum() / denominator, 0, 1)) if denominator > 0 else 0.0
    residual = np.abs(f - (a + weight * span)).max(axis=1)
    endpoint = min(float(np.abs(f - a).max(axis=1).mean()), float(np.abs(f - b).max(axis=1).mean()))
    mean = float(residual.mean())
    p98 = float(np.percentile(residual, 98))
    matched = (BLEND_MIN <= weight <= BLEND_MAX and endpoint_difference >= BLEND_MIN_ENDPOINT_DIFFERENCE
               and mean <= BLEND_MEAN_RESIDUAL and p98 <= BLEND_P98_RESIDUAL
               and mean <= BLEND_IMPROVEMENT * endpoint)
    return {"weight": round(weight, 4), "mean_residual": round(mean, 3), "p98_residual": round(p98, 3),
            "endpoint_residual": round(endpoint, 3), "endpoint_difference": round(endpoint_difference, 3),
            "matched": bool(matched)}


class FrameClassifier:
    def __init__(self, home: Image.Image, hierarchy: ET.Element, theme: str,
                 size: tuple[int, int], baseline: Image.Image | None = None):
        self.size = size
        self.reference = resized(home, size)
        self.home_patches = []
        self.home_bounds = []
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
            self.home_bounds.append((label, (max(0, x1 - 2), max(0, y1 - 2), min(size[0], x2 + 2), min(size[1], y2 + 2))))
        fixtures = Path(__file__).with_name("startup_visual_fixtures")
        # Original emulator is 720x1560; normalize both fixture and real frame.
        with Image.open(fixtures / f"native-logo-{theme}.png") as artwork:
            self.logo = edges(resized(artwork, (168, 168)))
            self.logo_transforms = [(scale, edges(resized(artwork, (round(168 * scale), round(168 * scale)))))
                                    for scale in SURFACE_SCALES if scale != 1]
        # Separate preparation UI (the diffuse glass launch shell), never a home reference.
        # Two independent visible text crops plus the surrounding diffuse field prevent
        # blank, flat, title-only or home surfaces from qualifying as this stage.
        with Image.open(fixtures / f"native-shell-{theme}.png") as shell:
            self.shell_reference = resized(shell, size)
        with Image.open(fixtures / f"native-splash-{theme}.png") as splash:
            self.splash_reference = resized(splash, size)
        self.shell_patches = []
        shell_edges = edges(self.shell_reference)
        scaled_text = []
        for bounds in SHELL_TEXT_BOUNDS:
            x1, y1, x2, y2 = (round(value * size[index % 2] / (360 if index % 2 == 0 else 780))
                              for index, value in enumerate(bounds))
            scaled_text.append((x1, y1, x2, y2))
            reference_crop = self.shell_reference[y1:y2, x1:x2].astype(np.int16)
            background = np.median(reference_crop.reshape(-1, 3), axis=0).astype(np.int16)
            self.shell_patches.append(((x1, y1, x2, y2), shell_edges[y1:y2, x1:x2], background))
        card = tuple(round(value * size[index % 2] / (360 if index % 2 == 0 else 780))
                     for index, value in enumerate(SHELL_CARD_BOUNDS))
        self.shell_field_mask = field_mask(size, (card, *scaled_text))
        self.blend_mask = field_mask(size, (card,))
        self.shell_field = field(self.shell_reference)
        self.splash_field = field(self.splash_reference)
        self.home_field = field(self.reference)
        self.home_transforms = []
        for scale in SURFACE_SCALES:
            scaled_size = tuple(round(value * scale) for value in size)
            scaled_edges = edges(resized(home, scaled_size))
            patches = []
            for label, bounds in self.home_bounds:
                x1, y1, x2, y2 = (round(value * scaled_size[index % 2] / size[index % 2]) for index, value in enumerate(bounds))
                origin = (x1 + round((size[0] - scaled_size[0]) / 2), y1 + round((size[1] - scaled_size[1]) / 2))
                patches.append((label, origin, scaled_edges[y1:y2, x1:x2].copy()))
            self.home_transforms.append((scale, patches))
        self.full_home_transform = next(transform for transform in self.home_transforms if transform[0] == 1)
        self.baseline = edges(resized(baseline, size)) if baseline is not None else None

    def home_transform_match(self, frame: np.ndarray, transform: tuple) -> dict:
        """Both semantic crops must match one scale and one shared translation."""
        scale, patches = transform
        height, width = frame.shape
        dx1 = max(-SURFACE_SHIFT[0], *[-origin[0] for _, origin, _ in patches])
        dy1 = max(-SURFACE_SHIFT[1], *[-origin[1] for _, origin, _ in patches])
        dx2 = min(SURFACE_SHIFT[0], *[width - origin[0] - template.shape[1] for _, origin, template in patches])
        dy2 = min(SURFACE_SHIFT[1], *[height - origin[1] - template.shape[0] for _, origin, template in patches])
        if dx2 < dx1 or dy2 < dy1:
            return {"score": 0.0, "scale": scale, "dx": None, "dy": None, "scores": {label: 0.0 for label, _, _ in patches}}
        maps = []
        for _, (x, y), template in patches:
            maps.append(match_scores(frame[y + dy1:y + template.shape[0] + dy2, x + dx1:x + template.shape[1] + dx2], template))
        if any(not scores.size for scores in maps):
            return {"score": 0.0, "scale": scale, "dx": None, "dy": None, "scores": {label: 0.0 for label, _, _ in patches}}
        combined = np.minimum.reduce(maps)
        y, x = np.unravel_index(combined.argmax(), combined.shape)
        return {"score": float(combined[y, x]), "scale": scale, "dx": int(x + dx1), "dy": int(y + dy1),
                "scores": {label: float(scores[y, x]) for (label, _, _), scores in zip(patches, maps)}}

    def logo_transform_match(self, frame: np.ndarray, scale: float, template: np.ndarray) -> dict:
        height, width = frame.shape
        th, tw = template.shape
        px, py = round((width - tw) / 2), round((height - th) / 2)
        dx1, dx2 = max(-SURFACE_SHIFT[0], -px), min(SURFACE_SHIFT[0], width - px - tw)
        dy1, dy2 = max(-SURFACE_SHIFT[1], -py), min(SURFACE_SHIFT[1], height - py - th)
        scores = match_scores(frame[py + dy1:py + th + dy2, px + dx1:px + tw + dx2], template)
        if not scores.size:
            return {"score": 0.0, "scale": scale, "dx": None, "dy": None}
        y, x = np.unravel_index(scores.argmax(), scores.shape)
        return {"score": float(scores[y, x]), "scale": scale, "dx": int(x + dx1), "dy": int(y + dy1)}

    def shell_match(self, frame: np.ndarray, edge_frame: np.ndarray, frame_field: np.ndarray) -> dict:
        scores = [match_score(edge_frame[y1:y2, x1:x2], template)
                  for (x1, y1, x2, y2), template, _ in self.shell_patches]
        # Normalized edge correlation is contrast invariant. Also require
        # visible ink, or almost-erased words could pass as a nonblank shell.
        contrast_ratios = []
        ink_ratios = []
        for (x1, y1, x2, y2), _, background in self.shell_patches:
            reference_contrast = np.max(np.abs(self.shell_reference[y1:y2,x1:x2].astype(np.int16) - background), axis=2)
            actual_contrast = np.max(np.abs(frame[y1:y2,x1:x2].astype(np.int16) - background), axis=2)
            reference_peak = float(np.percentile(reference_contrast, 95))
            contrast_ratios.append(float(np.percentile(actual_contrast,95)) / max(reference_peak,1))
            ink_threshold = max(12, reference_peak * .25)
            reference_ink = int(np.sum(reference_contrast >= ink_threshold))
            ink_ratios.append(int(np.sum(actual_contrast >= ink_threshold)) / max(reference_ink,1))
        difference = np.abs(frame_field - self.shell_field).max(axis=2)[self.shell_field_mask]
        field_mean = float(difference.mean())
        field_fraction = float(np.mean(difference <= FIELD_CELL_TOLERANCE))
        return {"text_scores": scores, "text_contrast_ratios": contrast_ratios, "text_ink_ratios": ink_ratios,
                "field_mean_difference": round(field_mean, 3), "field_cell_fraction": round(field_fraction, 4),
                "matched": min(scores) >= SHELL_TEXT_MATCH and min(contrast_ratios) >= .75
                    and min(ink_ratios) >= .75 and field_mean <= FIELD_MEAN_TOLERANCE
                    and field_fraction >= FIELD_CELL_FRACTION}

    def blend_match(self, frame_field: np.ndarray) -> dict:
        """Platform splash dissolving into the shell, or the shell crossfading into home."""
        fits = {"splash_to_shell": blend_fit(frame_field, self.splash_field, self.shell_field, self.blend_mask),
                "shell_to_home": blend_fit(frame_field, self.shell_field, self.home_field, self.blend_mask)}
        return {**fits, "matched": any(fit["matched"] for fit in fits.values())}

    def classify(self, frame: np.ndarray) -> dict:
        height, width, _ = frame.shape
        interior = frame[int(height * .06):int(height * .94), int(width * .04):int(width * .96)]
        black_fraction = float(np.mean(interior.max(axis=2) < 8))
        edge_frame = edges(frame)
        frame_field = field(frame)
        shell = self.shell_match(frame, edge_frame, frame_field)
        blend = {"matched": False}
        logo_score = match_score(edge_frame[int(height * .32):int(height * .69), int(width * .20):int(width * .80)], self.logo)
        home_match = self.home_transform_match(edge_frame, self.full_home_transform)
        logo_transform = {"score": logo_score, "scale": 1.0}
        baseline_score = 0.0
        if self.baseline is not None:
            area = edge_frame[int(height * .06):int(height * .94)]
            template = self.baseline[int(height * .06):int(height * .94)]
            baseline_score = match_score(area, template)
        if black_fraction >= .995:
            state = "black-blank"
        elif shell["matched"]:
            # Wordmark text only exists in the launch shell; its card holds the same icon
            # tile as the splash orb, so the shell is recognized before logo matching.
            state = "startup-shell"
        elif logo_score >= LOGO_MATCH:
            state = "native-logo"
        else:
            # Logo search precedes home, including transformed logos returning
            # over already-visible content or on a same-process warm resume.
            for scale, artwork in self.logo_transforms:
                match = self.logo_transform_match(edge_frame, scale, artwork)
                if match["score"] > logo_transform["score"]:
                    logo_transform = match
            if logo_transform["score"] >= TRANSITION_MATCH:
                state = "logo-transition"
            elif home_match["score"] >= HOME_MATCH:
                state = "home"
            else:
                for transform in self.home_transforms:
                    match = self.home_transform_match(edge_frame, transform)
                    if match["score"] > home_match["score"]:
                        home_match = match
                if home_match["score"] >= TRANSITION_MATCH:
                    state = "home-transition"
                elif baseline_score >= .95:
                    state = "prelaunch"
                else:
                    blend = self.blend_match(frame_field)
                    state = "shell-transition" if blend["matched"] else "unclassified"
        return {"state": state, "shell_match": shell, "blend_match": blend, "logo_score": round(logo_score, 5),
                "home_scores": {key: round(value, 5) for key, value in home_match["scores"].items()},
                "home_transform": {key: round(value, 5) if isinstance(value, float) else value for key, value in home_match.items() if key != "scores"},
                "logo_transform": {key: round(value, 5) if isinstance(value, float) else value for key, value in logo_transform.items()},
                "baseline_score": round(baseline_score, 5), "black_fraction": round(black_fraction, 5)}


def timeline_verdict(frames: list[dict], *, warm: bool = False) -> dict:
    errors = []
    home_seen = False
    full_home_seen = False
    logo_seen = False
    native_logo_seen = False
    shell_seen = False
    for frame in frames:
        state = frame["state"]
        stamp = f"frame {frame['frame']} at {frame['seconds']:.6f}s"
        if state in ("native-logo", "logo-transition"):
            if home_seen:
                errors.append(f"Native logo returned after visible home: {stamp}")
            if shell_seen:
                errors.append(f"Native logo returned after preparation shell: {stamp}")
            if warm:
                errors.append(f"Warm same-process resume displayed branded startup: {stamp}")
            logo_seen = True
            native_logo_seen |= state == "native-logo"
        if state == "startup-shell":
            if warm:
                errors.append(f"Warm same-process resume displayed preparation shell: {stamp}")
            if home_seen:
                errors.append(f"Preparation shell returned after visible home: {stamp}")
            if not native_logo_seen:
                errors.append(f"Preparation shell lacked preceding native-logo coverage: {stamp}")
            shell_seen = True
        if state == "shell-transition":
            if warm:
                errors.append(f"Warm same-process resume displayed launch shell transition: {stamp}")
            if full_home_seen:
                errors.append(f"Preparation shell returned after visible home: {stamp}")
            if not native_logo_seen:
                errors.append(f"Launch shell transition lacked preceding native-logo coverage: {stamp}")
        if state in ("home", "home-transition"):
            home_seen = True
            full_home_seen |= state == "home"
        if state == "black-blank":
            errors.append(f"Black blank screen: {stamp}")
        if state == "unclassified":
            errors.append(f"Unclassified visual evidence: {stamp}")
        if state == "prelaunch" and (logo_seen or shell_seen or home_seen):
            errors.append(f"Launch returned to the previous surface: {stamp}")
    if not home_seen:
        errors.append("Recording never established visible real home content")
    if not warm and not native_logo_seen:
        errors.append("Insufficient cold-start coverage: recording never established native-logo")
    if not frames or frames[-1]["state"] != "home":
        errors.append("Recording did not finish with visible real home content")
    return {"passed": not errors, "errors": errors, "home_seen": home_seen,
            "logo_seen": logo_seen, "native_logo_seen": native_logo_seen, "shell_seen": shell_seen,
            "unclassified_frames": sum(frame["state"] == "unclassified" for frame in frames)}


def original_timestamps(frames: list[dict]) -> list[float]:
    """Require a complete, ordered original presentation timeline."""
    timestamps = []
    for index, frame in enumerate(frames):
        try:
            stamp = float(frame["best_effort_timestamp_time"])
        except (KeyError, TypeError, ValueError) as error:
            raise RuntimeError(f"Original frame {index} has no valid presentation timestamp") from error
        if not math.isfinite(stamp) or stamp < 0:
            raise RuntimeError(f"Original frame {index} has nonfinite or negative presentation timestamp: {stamp}")
        if timestamps and stamp <= timestamps[-1]:
            raise RuntimeError(f"Original frame {index} has nonincreasing presentation timestamp: {stamp}")
        timestamps.append(stamp)
    return timestamps


def inspect_recording(video: Path, home: Path, hierarchy: Path, theme: str, output: Path,
                      *, baseline: Path | None = None, warm: bool = False) -> dict:
    frames = []
    result = {"video": video.name, "sha256": None,
              "scope": "Every original decoded frame and presentation timestamp; real semantic home and native artwork image matching",
              "theme": theme, "warm_same_process": warm,
              "thresholds": {"logo": LOGO_MATCH, "home": HOME_MATCH, "recognized_transition": TRANSITION_MATCH, "shell_text": SHELL_TEXT_MATCH,
                             "shell_min_text_contrast_ratio": .75, "shell_min_text_ink_ratio": .75,
                             "shell_field_cell_pixels": FIELD_CELL, "shell_field_mean_tolerance": FIELD_MEAN_TOLERANCE,
                             "shell_field_cell_tolerance": FIELD_CELL_TOLERANCE, "shell_field_cell_fraction": FIELD_CELL_FRACTION,
                             "blend_weight_range": [BLEND_MIN, BLEND_MAX], "blend_mean_residual": BLEND_MEAN_RESIDUAL,
                             "blend_p98_residual": BLEND_P98_RESIDUAL, "blend_improvement": BLEND_IMPROVEMENT},
              "surface_transform_bounds": {"scale_min": min(SURFACE_SCALES), "scale_max": max(SURFACE_SCALES),
                                           "scale_step": .005, "shared_home_translation_pixels": list(SURFACE_SHIFT)}}
    try:
        result["sha256"] = hashlib.sha256(video.read_bytes()).hexdigest()
        probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height:frame=best_effort_timestamp_time", "-of", "json", str(video)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        probe_error = probe.stderr.decode("utf-8", "replace")
        result["probe"] = {"returncode": probe.returncode, "stderr": probe_error}
        if probe.returncode or probe_error.strip():
            raise RuntimeError(f"Original frame probe failed (exit {probe.returncode}): {probe_error}")
        info = json.loads(probe.stdout)
        result["original_timestamp_count"] = len(info["frames"])
        result["original_timestamps_valid"] = False
        timestamps = original_timestamps(info["frames"])
        result["original_timestamps_valid"] = True
        stream = info["streams"][0]
        size = (MATCH_WIDTH, round(stream["height"] * MATCH_WIDTH / stream["width"]))
        if abs(size[1] / size[0] - 1560 / 720) > .02:
            raise RuntimeError("Startup artwork matching requires the recorded portrait emulator aspect ratio")
        with ExitStack() as references:
            home_image = references.enter_context(Image.open(home))
            baseline_image = references.enter_context(Image.open(baseline)) if baseline is not None else None
            classifier = FrameClassifier(home_image, ET.parse(hierarchy).getroot(), theme, size, baseline_image)
        # A file avoids a full stderr pipe blocking the decoder on damaged input.
        with tempfile.TemporaryFile() as decoder_errors:
            process = subprocess.Popen(["ffmpeg", "-v", "error", "-i", str(video), "-vsync", "0",
                # Keep variable-rate PTS precise; default 1/framerate can round
                # distinct input timestamps into equal rawvideo muxer DTS.
                "-vf", f"scale={size[0]}:{size[1]}", "-enc_time_base", "demux",
                "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
                stdout=subprocess.PIPE, stderr=decoder_errors)
            try:
                for index, stamp in enumerate(timestamps):
                    data = process.stdout.read(size[0] * size[1] * 3)
                    if len(data) != size[0] * size[1] * 3:
                        raise RuntimeError("Decoder omitted or truncated an original video frame")
                    classification = classifier.classify(np.frombuffer(data, dtype=np.uint8).reshape(size[1], size[0], 3))
                    frames.append({"frame": index, "seconds": stamp, **classification})
                if process.stdout.read(1):
                    raise RuntimeError("Decoded frame count differs from the original presentation timestamps")
                process.wait(timeout=10)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
                process.stdout.close()
                decoder_errors.seek(0)
                decoder_error = decoder_errors.read().decode("utf-8", "replace")
                result["decoder"] = {"returncode": process.returncode, "stderr": decoder_error}
            if process.returncode or decoder_error.strip():
                raise RuntimeError(f"Frame decoder failed (exit {process.returncode}): {decoder_error}")
        result.update(timeline_verdict(frames, warm=warm))
    except Exception as error:
        result.update(timeline_verdict(frames, warm=warm))
        result["passed"] = False
        result["evidence_error"] = f"{type(error).__name__}: {error}"
        result["errors"].insert(0, f"Visual evidence inspection failed: {result['evidence_error']}")
    gaps = [later["seconds"] - earlier["seconds"] for earlier, later in zip(frames, frames[1:])]
    first_home = next((frame["seconds"] for frame in frames if frame["state"] == "home"), None)
    result["sampling"] = {"max_original_frame_gap_seconds": max(gaps) if gaps else None,
                          "first_recorded_full_home_pts_seconds": first_home,
                          "continuous_display_between_frames": "unobserved",
                          "scope": "All recorded frames checked; this does not establish absence of black frames between recorded timestamps or App-only startup time"}
    result.update(frames_decoded=len(frames), frames=frames)
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
