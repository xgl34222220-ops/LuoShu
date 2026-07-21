#!/usr/bin/env python3
"""Geometry-aligned wrapper for LuoShu's composite font builder.

The base CJK font already contains Latin and digit glyphs whose cap height, x-height and baseline
were designed to sit correctly beside its CJK glyphs. The original composite builder replaced those
outlines using only unitsPerEm scaling, so visually small or vertically shifted source fonts could
look misaligned in mixed launcher labels.

This wrapper keeps the original horizontal metrics and spacing, but derives a bounded vertical scale
and baseline translation from the base font's existing Latin/digit glyphs before delegating to the
same proven outline conversion code. It intentionally does not change CJK glyphs, line metrics,
Emoji, symbols, icons or monospace system slots.
"""
from __future__ import annotations

import statistics
from typing import Iterable

from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

import composite_font as engine

LATIN_ALIGNMENT_PROBES = tuple(map(ord, "ABDEHIKLMNOPRSTUVXYZacehmnorsuvxz"))
DIGIT_ALIGNMENT_PROBES = tuple(map(ord, "0123456789"))
MIN_VERTICAL_FACTOR = 0.86
MAX_VERTICAL_FACTOR = 1.16
MAX_SHIFT_EM = 0.08

_current_x_scale = 1.0
_current_y_scale = 1.0
_current_y_shift = 0.0


def _glyph_bounds(glyph_set, cmap: dict[int, str], codepoint: int):
    name = cmap.get(codepoint)
    if not name or name not in glyph_set:
        return None
    pen = BoundsPen(glyph_set)
    glyph_set[name].draw(pen)
    return pen.bounds


def _median(values: list[float], fallback: float) -> float:
    return float(statistics.median(values)) if values else fallback


def _alignment_transform(
    base: TTFont,
    source: TTFont,
    source_glyph_set,
    probes: Iterable[int],
) -> tuple[float, float, float]:
    base_glyph_set = base.getGlyphSet()
    base_cmap = base.getBestCmap() or {}
    source_cmap = source.getBestCmap() or {}
    base_upem = float(base["head"].unitsPerEm)
    source_upem = float(source["head"].unitsPerEm)
    x_scale = base_upem / source_upem

    height_factors: list[float] = []
    for codepoint in probes:
        base_bounds = _glyph_bounds(base_glyph_set, base_cmap, codepoint)
        source_bounds = _glyph_bounds(source_glyph_set, source_cmap, codepoint)
        if base_bounds is None or source_bounds is None:
            continue
        base_height = float(base_bounds[3] - base_bounds[1])
        source_height = float(source_bounds[3] - source_bounds[1]) * x_scale
        if base_height <= 0 or source_height <= 0:
            continue
        height_factors.append(base_height / source_height)

    vertical_factor = min(MAX_VERTICAL_FACTOR, max(MIN_VERTICAL_FACTOR, _median(height_factors, 1.0)))
    y_scale = x_scale * vertical_factor

    bottom_shifts: list[float] = []
    for codepoint in probes:
        base_bounds = _glyph_bounds(base_glyph_set, base_cmap, codepoint)
        source_bounds = _glyph_bounds(source_glyph_set, source_cmap, codepoint)
        if base_bounds is None or source_bounds is None:
            continue
        bottom_shifts.append(float(base_bounds[1]) - float(source_bounds[1]) * y_scale)

    max_shift = base_upem * MAX_SHIFT_EM
    y_shift = min(max_shift, max(-max_shift, _median(bottom_shifts, 0.0)))
    return x_scale, y_scale, y_shift


def _draw_decomposed_aligned(glyph_set, glyph_name: str, destination_pen, _scale: float) -> None:
    recorder = DecomposingRecordingPen(glyph_set)
    glyph_set[glyph_name].draw(recorder)
    recorder.replay(
        TransformPen(
            destination_pen,
            (_current_x_scale, 0, 0, _current_y_scale, 0, _current_y_shift),
        )
    )


def _replace_codepoints_aligned(
    base: TTFont,
    source: TTFont,
    codepoints: Iterable[int],
    location: dict[str, float] | None = None,
    required: set[int] | None = None,
) -> tuple[int, list[int]]:
    global _current_x_scale, _current_y_scale, _current_y_shift

    required = required or set()
    base_cmap = base.getBestCmap() or {}
    source_cmap = source.getBestCmap() or {}
    source_glyph_set = source.getGlyphSet(location=location) if location else source.getGlyphSet()
    base_kind = engine._outline_kind(base)
    probes = DIGIT_ALIGNMENT_PROBES if required == engine.REQUIRED_DIGITS else LATIN_ALIGNMENT_PROBES
    x_scale, y_scale, y_shift = _alignment_transform(base, source, source_glyph_set, probes)

    replaced = 0
    missing: list[int] = []
    already: set[str] = set()
    previous = (_current_x_scale, _current_y_scale, _current_y_shift)
    _current_x_scale, _current_y_scale, _current_y_shift = x_scale, y_scale, y_shift
    try:
        for codepoint in sorted(codepoints):
            base_name = base_cmap.get(codepoint)
            source_name = source_cmap.get(codepoint)
            if not base_name or not source_name:
                if codepoint in required:
                    raise engine.CompositeError(
                        f"源字体或中文基底缺少必要字符 U+{codepoint:04X}"
                    )
                missing.append(codepoint)
                continue

            key = f"{base_name}:{source_name}"
            if key in already:
                continue
            already.add(key)

            try:
                advance, lsb = source["hmtx"].metrics[source_name]
                variable_width = getattr(source_glyph_set[source_name], "width", None)
                if isinstance(variable_width, (int, float)):
                    advance = variable_width
            except (KeyError, TypeError):
                missing.append(codepoint)
                continue

            # Horizontal layout deliberately stays identical to the original engine. Only glyph
            # outlines are vertically normalized, so launcher labels do not become wider or wrap.
            advance = int(round(float(advance) * x_scale))
            lsb = int(round(float(lsb) * x_scale))
            try:
                if base_kind == "glyf":
                    engine._replace_glyf(
                        base,
                        source,
                        source_glyph_set,
                        base_name,
                        source_name,
                        x_scale,
                    )
                else:
                    engine._replace_cff(
                        base,
                        source,
                        source_glyph_set,
                        base_name,
                        source_name,
                        x_scale,
                        advance,
                    )
            except Exception as exc:
                if codepoint in required:
                    raise engine.CompositeError(
                        f"必要字符 U+{codepoint:04X} 的字形转换失败：{exc}"
                    ) from exc
                missing.append(codepoint)
                continue

            base["hmtx"].metrics[base_name] = (advance, lsb)
            replaced += 1
    finally:
        _current_x_scale, _current_y_scale, _current_y_shift = previous

    return replaced, missing


engine._draw_decomposed = _draw_decomposed_aligned
engine._replace_codepoints = _replace_codepoints_aligned


if __name__ == "__main__":
    raise SystemExit(engine.main())
