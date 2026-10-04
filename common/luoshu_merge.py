#!/usr/bin/env python3
"""Copy Latin and digit glyphs into a CJK base font (engine v3 composite).

Ported from the legacy composite builder that shipped on devices: the CJK font
stays the complete base, Latin and digit outlines are drawn into glyph slots
that already exist in the base, scaled to the base cap height and moved onto
the baseline. The output keeps one complete cmap.
"""
from __future__ import annotations

import math
import statistics
from typing import Iterable

from fontTools.pens.basePen import NullPen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.qu2cuPen import Qu2CuPen
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

DIGIT_CODEPOINTS = frozenset(
    set(range(0x0030, 0x003A))
    | set(range(0xFF10, 0xFF1A))
    | {0x00B2, 0x00B3, 0x00B9}
    | set(range(0x2070, 0x207A))
    | set(range(0x2080, 0x208A))
)
LATIN_CODEPOINTS = frozenset((
    set(range(0x0020, 0x0030))
    | set(range(0x003A, 0x007F))
    | set(range(0x00A0, 0x0250))
    | set(range(0x0300, 0x0370))
    | set(range(0x1E00, 0x1F00))
    | set(range(0x2000, 0x2070))
    | set(range(0x20A0, 0x20D0))
    | set(range(0x2100, 0x2150))
) - DIGIT_CODEPOINTS)
REQUIRED = {
    "latin": frozenset(map(ord, "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")),
    "digit": frozenset(map(ord, "0123456789")),
}
# Flat-bottom probes: O/0/8/9 overshoot the baseline and would bias the shift.
FLAT_BOTTOM_PROBES = {"latin": "HIEX", "digit": "147"}
BASELINE_SHIFT_LIMIT_RATIO = 0.25


class MergeError(RuntimeError):
    pass


def outline_kind(font: TTFont) -> str:
    for tag, kind in (("glyf", "glyf"), ("CFF ", "cff"), ("CFF2", "cff2")):
        if tag in font:
            return kind
    raise MergeError("字体不包含受支持的 glyf、CFF 或 CFF2 轮廓")


def _bounds(font: TTFont, glyph_set, codepoint: int):
    name = (font.getBestCmap() or {}).get(codepoint)
    if not name or name not in glyph_set:
        return None
    pen = BoundsPen(glyph_set)
    glyph_set[name].draw(pen)
    return None if pen.bounds is None else tuple(float(value) for value in pen.bounds)


def _role_transform(base: TTFont, src: TTFont, src_glyph_set, role: str) -> tuple[float, float]:
    base_glyph_set = base.getGlyphSet()
    upem_scale = base["head"].unitsPerEm / src["head"].unitsPerEm
    ratios = []
    for codepoint in map(ord, "AHIOXEx" if role == "latin" else "0189"):
        base_box = _bounds(base, base_glyph_set, codepoint)
        src_box = _bounds(src, src_glyph_set, codepoint)
        if base_box and src_box and src_box[3] > src_box[1] and base_box[3] > base_box[1]:
            ratios.append((base_box[3] - base_box[1]) / ((src_box[3] - src_box[1]) * upem_scale))
    if not ratios:
        return upem_scale, 0.0
    scale = upem_scale * max(0.82, min(1.18, float(statistics.median(ratios))))
    bottoms = [box[1] for box in (
        _bounds(src, src_glyph_set, codepoint) for codepoint in map(ord, FLAT_BOTTOM_PROBES[role])
    ) if box]
    if not bottoms:
        return scale, 0.0
    # The baseline is y=0; only correct a genuine source displacement.
    shift = -float(statistics.median(bottoms)) * scale
    limit = base["head"].unitsPerEm * BASELINE_SHIFT_LIMIT_RATIO
    return scale, max(-limit, min(limit, shift))


def _enclose_bounds(font: TTFont, bounds) -> None:
    if bounds is None:
        return
    box = (math.floor(bounds[0]), math.floor(bounds[1]), math.ceil(bounds[2]), math.ceil(bounds[3]))
    head = font["head"]
    head.xMin = min(head.xMin, box[0]); head.yMin = min(head.yMin, box[1])
    head.xMax = max(head.xMax, box[2]); head.yMax = max(head.yMax, box[3])
    for tag in ("CFF ", "CFF2"):
        if tag in font:
            top = font[tag].cff.topDictIndex[0]
            if hasattr(top, "FontBBox"):
                prior = top.FontBBox
                top.FontBBox = [min(prior[0], box[0]), min(prior[1], box[1]),
                                max(prior[2], box[2]), max(prior[3], box[3])]


def _clear_metric_variations(font: TTFont, glyph_name: str) -> None:
    """An imported static glyph must not inherit the old glyph's HVAR/VVAR deltas."""
    if "HVAR" not in font and "VVAR" not in font:
        return
    from fontTools.ttLib.tables.otTables import NO_VARIATION_INDEX
    from fontTools.varLib.builder import buildVarIdxMap
    for tag, fields in (("HVAR", ("AdvWidthMap", "LsbMap", "RsbMap")),
                        ("VVAR", ("AdvHeightMap", "TsbMap", "BsbMap", "VOrgMap"))):
        if tag not in font:
            continue
        table = font[tag].table
        for field in fields:
            mapping = getattr(table, field, None)
            if mapping is None:
                if field != fields[0]:
                    continue
                order = font.getGlyphOrder()
                mapping = buildVarIdxMap(range(len(order)), order)
                setattr(table, field, mapping)
            mapping.mapping[glyph_name] = NO_VARIATION_INDEX


def _draw(glyph_set, name: str, pen, scale: float, shift: float) -> None:
    recorder = DecomposingRecordingPen(glyph_set)
    glyph_set[name].draw(recorder)
    recorder.replay(TransformPen(pen, (scale, 0, 0, scale, 0, shift)))


def _replace_glyf(base: TTFont, src_kind: str, glyph_set, base_name: str, src_name: str,
                  scale: float, shift: float) -> None:
    pen = TTGlyphPen(None)
    _draw(glyph_set, src_name, Cu2QuPen(pen, max_err=max(0.5, base["head"].unitsPerEm / 2000),
                                        reverse_direction=src_kind in {"cff", "cff2"}), scale, shift)
    glyph = pen.glyph()
    base["glyf"][base_name] = glyph
    glyph.recalcBounds(base["glyf"])
    if not hasattr(glyph, "xMin"):
        glyph.xMin = glyph.yMin = glyph.xMax = glyph.yMax = 0
    _enclose_bounds(base, (glyph.xMin, glyph.yMin, glyph.xMax, glyph.yMax))
    if "gvar" in base:
        base["gvar"].variations.pop(base_name, None)


def _replace_cff(base: TTFont, src_kind: str, glyph_set, base_name: str, src_name: str,
                 scale: float, shift: float, width: int) -> None:
    tag = "CFF " if "CFF " in base else "CFF2"
    cff = base[tag].cff
    top = cff.topDictIndex[0]
    _old, selector = top.CharStrings.getItemAndSelector(base_name)
    private = top.FDArray[selector or 0].Private if hasattr(top, "FDArray") else top.Private
    is_cff2 = tag == "CFF2"
    pen = T2CharStringPen(None if is_cff2 else width, None, CFF2=is_cff2)
    _draw(glyph_set, src_name, Qu2CuPen(pen, max_err=max(0.5, base["head"].unitsPerEm / 2000),
                                        all_cubic=True, reverse_direction=src_kind == "glyf"), scale, shift)
    charstring = pen.getCharString(private=private, globalSubrs=cff.GlobalSubrs)
    if selector is not None:
        charstring.fdSelectIndex = selector
    top.CharStrings[base_name] = charstring
    _enclose_bounds(base, charstring.calcBounds(top.CharStrings))


def import_glyphs(base: TTFont, src: TTFont, role: str, location: dict[str, float] | None = None) -> int:
    """Draws the role's glyphs from ``src`` into ``base``; returns the count."""
    codepoints: Iterable[int] = LATIN_CODEPOINTS if role == "latin" else DIGIT_CODEPOINTS
    required = REQUIRED[role]
    base_cmap = base.getBestCmap() or {}
    src_cmap = src.getBestCmap() or {}
    glyph_set = src.getGlyphSet(location=location) if location else src.getGlyphSet()
    base_kind, src_kind = outline_kind(base), outline_kind(src)
    scale, shift = _role_transform(base, src, glyph_set, role)
    replaced = 0
    done: set[tuple[str, str]] = set()
    for codepoint in sorted(codepoints):
        base_name, src_name = base_cmap.get(codepoint), src_cmap.get(codepoint)
        if not base_name or not src_name:
            if codepoint in required:
                raise MergeError(f"源字体或中文基底缺少必要字符 U+{codepoint:04X}")
            continue
        if (base_name, src_name) in done:
            continue
        done.add((base_name, src_name))
        try:
            advance, lsb = src["hmtx"].metrics[src_name]
            # Without HVAR the varied advance is only known after drawing.
            sampled = glyph_set[src_name]
            sampled.draw(NullPen())
            width = getattr(sampled, "width", None)
            if isinstance(width, (int, float)):
                advance = width
        except (KeyError, TypeError):
            continue
        advance = int(round(float(advance) * scale))
        lsb = int(round(float(lsb) * scale))
        try:
            if base_kind == "glyf":
                _replace_glyf(base, src_kind, glyph_set, base_name, src_name, scale, shift)
            else:
                _replace_cff(base, src_kind, glyph_set, base_name, src_name, scale, shift, advance)
        except Exception as error:
            if codepoint in required:
                raise MergeError(f"必要字符 U+{codepoint:04X} 的字形转换失败：{error}") from error
            continue
        base["hmtx"].metrics[base_name] = (advance, lsb)
        _clear_metric_variations(base, base_name)
        replaced += 1
    if replaced < len(required):
        raise MergeError(f"{'英文' if role == 'latin' else '数字'}替换数量异常（仅 {replaced} 个）")
    return replaced


# ------------------------------------------------------------ variable import
#
# A variable CJK base keeps its wght axis; Latin/digit glyphs are drawn from a
# variable source at a few base weights and stored as gvar deltas, so one
# output serves every weight instead of one static font per weight.

VARIABLE_SAMPLES = (-1.0, -0.5, 0.0, 0.5, 1.0)


def can_vary(base: TTFont, src: TTFont | None) -> bool:
    """Whether ``src`` glyphs can be imported into ``base`` with variations."""
    if "glyf" not in base or "gvar" not in base or "fvar" not in base:
        return False
    if not any(axis.axisTag == "wght" for axis in base["fvar"].axes):
        return False
    if src is None:
        return True
    return "glyf" in src and "fvar" in src and any(axis.axisTag == "wght" for axis in src["fvar"].axes)


def _axis(font: TTFont, tag: str):
    return next(axis for axis in font["fvar"].axes if axis.axisTag == tag)


def _user_weight(base: TTFont, normalized: float) -> float:
    """Base user-space wght for a normalized coordinate (inverting avar)."""
    if "avar" in base:
        segments = base["avar"].segments.get("wght") or {}
        points = sorted(segments.items())
        if len(points) >= 2:
            # avar maps input->output; invert piecewise-linearly.
            for (in_a, out_a), (in_b, out_b) in zip(points, points[1:]):
                if out_a <= normalized <= out_b and out_b != out_a:
                    normalized = in_a + (normalized - out_a) * (in_b - in_a) / (out_b - out_a)
                    break
    axis = _axis(base, "wght")
    if normalized < 0:
        return axis.defaultValue + normalized * (axis.defaultValue - axis.minValue)
    return axis.defaultValue + normalized * (axis.maxValue - axis.defaultValue)


def _sample(glyph_set, name: str, scale: float, shift: float, fallback_width: float):
    """Glyph outline and advance at the glyph set's location.

    The advance must be read from the same glyph object after drawing: without
    HVAR, fontTools derives it from the gvar phantom points while drawing.
    """
    source = glyph_set[name]
    recorder = DecomposingRecordingPen(glyph_set)
    source.draw(recorder)
    pen = TTGlyphPen(None)
    recorder.replay(TransformPen(pen, (scale, 0, 0, scale, 0, shift)))
    width = getattr(source, "width", None)
    if not isinstance(width, (int, float)):
        width = fallback_width
    return pen.glyph(), int(round(float(width) * scale))


def import_glyphs_variable(base: TTFont, src: TTFont, role: str, fixed: dict[str, float] | None = None) -> int:
    """Like :func:`import_glyphs` but keeps the source's weight variation.

    ``fixed`` pins the source (fixed mode or a static source): glyphs are
    imported static and stay the same at every base weight.
    """
    from fontTools.misc.vector import Vector
    from fontTools.ttLib.tables.TupleVariation import TupleVariation
    from fontTools.varLib.models import VariationModel

    codepoints: Iterable[int] = LATIN_CODEPOINTS if role == "latin" else DIGIT_CODEPOINTS
    required = REQUIRED[role]
    base_cmap = base.getBestCmap() or {}
    src_cmap = src.getBestCmap() or {}
    src_axes = {axis.axisTag: axis for axis in src["fvar"].axes} if "fvar" in src else {}

    def src_location(user_weight: float) -> dict[str, float] | None:
        if not src_axes:
            return None
        location = {tag: axis.defaultValue for tag, axis in src_axes.items()}
        if fixed:
            location.update({tag: value for tag, value in fixed.items() if tag in location})
        elif "wght" in src_axes:
            axis = src_axes["wght"]
            location["wght"] = max(axis.minValue, min(axis.maxValue, user_weight))
        return location

    samples = [0.0] if fixed is not None or not src_axes else list(VARIABLE_SAMPLES)
    default_weight = _axis(base, "wght").defaultValue
    glyph_sets = {value: src.getGlyphSet(location=src_location(_user_weight(base, value)))
                  for value in samples}
    scale, shift = _role_transform(base, src, glyph_sets[0.0], role)
    model = VariationModel([{} if value == 0.0 else {"wght": value} for value in samples], axisOrder=["wght"])
    gvar = base["gvar"]
    glyf = base["glyf"]
    replaced = 0
    done: set[tuple[str, str]] = set()
    for codepoint in sorted(codepoints):
        base_name, src_name = base_cmap.get(codepoint), src_cmap.get(codepoint)
        if not base_name or not src_name:
            if codepoint in required:
                raise MergeError(f"源字体或中文基底缺少必要字符 U+{codepoint:04X}")
            continue
        if (base_name, src_name) in done:
            continue
        done.add((base_name, src_name))
        try:
            sampled = [_sample(glyph_sets[value], src_name, scale, shift, src["hmtx"].metrics[src_name][0])
                       for value in samples]
            glyphs = [glyph for glyph, _ in sampled]
            advances = [advance for _, advance in sampled]
            coordinates = []
            for glyph, advance in zip(glyphs, advances):
                points, ends, _flags = glyph.getCoordinates(glyf)
                coordinates.append((list(points), list(ends), advance))
            first_points, first_ends, _ = coordinates[0]
            if any(len(points) != len(first_points) or ends != first_ends for points, ends, _ in coordinates):
                raise MergeError("轮廓在不同字重下点数不一致")
        except MergeError:
            if codepoint in required:
                raise
            continue
        except Exception as error:
            if codepoint in required:
                raise MergeError(f"必要字符 U+{codepoint:04X} 的字形转换失败：{error}") from error
            continue
        default = glyphs[samples.index(0.0)]
        glyf[base_name] = default
        default.recalcBounds(glyf)
        if not hasattr(default, "xMin"):
            default.xMin = default.yMin = default.xMax = default.yMax = 0
        _enclose_bounds(base, (default.xMin, default.yMin, default.xMax, default.yMax))
        default_advance = advances[samples.index(0.0)]
        lsb = int(getattr(default, "xMin", 0))
        base["hmtx"].metrics[base_name] = (default_advance, lsb)
        variations = []
        if len(samples) > 1:
            # Master values: every point plus the four phantom points (advance last-but-two).
            masters = []
            for points, _ends, advance in coordinates:
                flat = [coordinate for point in points for coordinate in point]
                flat += [0, 0, advance, 0, 0, 0, 0, 0]
                masters.append(Vector(flat))
            deltas = model.getDeltas(masters)
            for support, delta in zip(model.supports[1:], deltas[1:]):
                pairs = [(int(round(delta[i])), int(round(delta[i + 1]))) for i in range(0, len(delta), 2)]
                if any(pairs):
                    variations.append(TupleVariation(support, pairs))
        gvar.variations[base_name] = variations
        replaced += 1
    if replaced < len(required):
        raise MergeError(f"{'英文' if role == 'latin' else '数字'}替换数量异常（仅 {replaced} 个）")
    # Advance variation for imported glyphs lives in gvar phantom points; HVAR
    # would override it, so drop HVAR and let every glyph use gvar.
    if "HVAR" in base:
        del base["HVAR"]
    return replaced
