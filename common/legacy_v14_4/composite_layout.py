"""Layout shared by the normal and compatibility composite engines.

Probe only a few Latin/digit glyphs; never walk/rebuild the untouched CJK face.
"""
from __future__ import annotations
import math
import statistics
from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont

def _bounds_for_codepoint(font: TTFont, glyph_set, codepoint: int) -> tuple[float, float, float, float] | None:
    glyph_name = (font.getBestCmap() or {}).get(codepoint)
    if not glyph_name or glyph_name not in glyph_set:
        return None
    pen = BoundsPen(glyph_set)
    glyph_set[glyph_name].draw(pen)
    return None if pen.bounds is None else tuple(float(value) for value in pen.bounds)


def validate_required_ink(font: TTFont, latin, digits, cjk_probes) -> dict:
    """Check bounded, visible text probes, rather than treating cmap as ink.

    Spaces, controls, combining marks and other optional glyphs may be empty.
    The inherited CJK cmap stays intact: only mapped CJK probes are drawn, with
    the existing mandatory U+4E2D check retained. This is not a full Han audit.
    """
    cmap = font.getBestCmap() or {}
    mandatory = set(latin) | set(digits) | {ord("中")}
    missing = sorted(cp for cp in mandatory if not cmap.get(cp) or cmap[cp] == ".notdef")
    if missing:
        raise ValueError(f"复合字体缺少必要字符 U+{missing[0]:04X}")
    points = mandatory | (set(cjk_probes) & cmap.keys())
    names = {cmap[cp] for cp in points}

    # Do not decode SVG documents or bitmap images just to validate ordinary
    # text. The composite engine copies outlines, not those drawing programs.
    unsupported = [tag for tag in ("CBDT", "CBLC", "EBDT", "EBLC", "sbix", "SVG ") if tag in font]
    if unsupported:
        raise ValueError("复合输出不支持 SVG 或位图文字绘制：" + ", ".join(unsupported))
    if "COLR" in font:
        colr = font["COLR"]
        color_names = set(getattr(colr, "ColorLayers", {}) or {})
        table = getattr(colr, "table", None)
        for attribute in ("BaseGlyphRecordArray", "BaseGlyphList"):
            records = getattr(table, attribute, None)
            records = (getattr(records, "BaseGlyphRecord", None)
                       or getattr(records, "BaseGlyphPaintRecord", None) or [])
            color_names.update(record.BaseGlyph for record in records)
        if names & color_names:
            raise ValueError("复合输出不支持必要文字依赖 COLR 彩色绘制")

    glyph_set = font.getGlyphSet()
    bounds_by_name = {}
    for cp in sorted(points):
        name = cmap[cp]
        if name not in bounds_by_name:
            if name == ".notdef" or name not in glyph_set:
                raise ValueError(f"复合字体的必要字符 U+{cp:04X} 没有可用字形")
            pen = BoundsPen(glyph_set)
            glyph_set[name].draw(pen)
            bounds_by_name[name] = pen.bounds
        bounds = bounds_by_name[name]
        if (bounds is None or not all(math.isfinite(value) for value in bounds)
                or bounds[2] <= bounds[0] or bounds[3] <= bounds[1]):
            raise ValueError(f"复合字体的必要字符 U+{cp:04X} 字形为空或没有可见面积")
    return {
        "bounds": {role: list(bounds_by_name[cmap[cp]])
                   for role, cp in (("cjk", ord("中")), ("latin", ord("A")), ("digit", ord("1")))},
        "inkValidation": {"method": "bounded-monochrome-outlines-v1",
                          "codepoints": len(points), "glyphsDrawn": len(bounds_by_name)},
    }


# Translation probes deliberately use flat-bottom glyphs. Rounded glyphs such as O/0/8/9
# overshoot the baseline and introduce a systematic upward bias (FLAT_HEIGHT_PROBES).
BASELINE_SHIFT_LIMIT_RATIO = 0.25


def clear_imported_metric_variations(font: TTFont, glyph_name: str) -> None:
    """Keep a copied static glyph independent of the replaced glyph's metrics.

    Removing its gvar outlines does not remove HVAR/VVAR deltas. In particular,
    HyperOS changes the selected weight with text size, exposing the old base
    glyph's advance variation on an otherwise static imported letter or digit.
    Override only this glyph's mapping; shared delta sets and CJK stay intact.
    """
    if 'HVAR' not in font and 'VVAR' not in font:
        return
    from fontTools.ttLib.tables.otTables import NO_VARIATION_INDEX
    from fontTools.varLib.builder import buildVarIdxMap

    for tag, fields in (
        ('HVAR', ('AdvWidthMap', 'LsbMap', 'RsbMap')),
        ('VVAR', ('AdvHeightMap', 'TsbMap', 'BsbMap', 'VOrgMap')),
    ):
        if tag not in font:
            continue
        table = font[tag].table
        for field in fields:
            mapping = getattr(table, field, None)
            if mapping is None:
                if field != fields[0]:
                    continue  # Missing optional side-bearing maps mean no delta.
                # Missing advance maps use glyph IDs as implicit delta indices.
                # Preserve that mapping for every untouched glyph before making
                # one imported glyph independent of the base variation store.
                order = font.getGlyphOrder()
                mapping = buildVarIdxMap(range(len(order)), order)
                setattr(table, field, mapping)
            mapping.mapping[glyph_name] = NO_VARIATION_INDEX


# Height probes have flat tops and flat bottoms in nearly every design. Round
# glyphs (O/0/8/9) and apexes (A) overshoot in humanist CJK companions such as
# MiSans/Noto but not in geometric or "tech" Latin fonts, which inflated the
# imported digits by 3-5 % against the letters and the CJK beside them.
FLAT_HEIGHT_PROBES = {"latin": "HIEXTLZ", "digit": "147"}
# Ideographs whose ink spans their design box; the median is the CJK box.
CJK_BOX_PROBES = "中国田日口目四回永"
# Where Latin sits against the ideographic box in MiSans, Noto/Source Han Sans
# and similar pairings: baseline about 8 % above the ideograph bottom.
CJK_BASELINE_RATIO = 0.08
CJK_BASELINE_TOLERANCE = 0.05
CJK_BASELINE_SHIFT_LIMIT_RATIO = 0.15
# Latin cap height against the ideographic box in the same pairings (MiSans,
# Noto/Source Han Sans, LXGW WenKai all measure 0.87-0.88). A CJK font whose own
# Latin is small next to large, full-bodied ideographs (round/cute designs) made
# imported Latin and digits look shrunken beside Han ("36岁").
CJK_CAP_RATIO = 0.88
CJK_CAP_TOLERANCE = 0.05
# Only enlarge: shrinking Latin a CJK font ships oversized is not this fix.
CJK_CAP_FACTOR_LIMITS = (1.0, 1.18)


def _median_flat_extents(font: TTFont, glyph_set, role: str):
    boxes = [box for box in (_bounds_for_codepoint(font, glyph_set, cp)
                             for cp in map(ord, FLAT_HEIGHT_PROBES.get(role, "")))
             if box and box[3] > box[1]]
    if not boxes:
        return None
    return (float(statistics.median(box[1] for box in boxes)),
            float(statistics.median(box[3] for box in boxes)))


def cjk_baseline_shift(base: TTFont, base_glyph_set=None) -> float:
    """Vertical move that seats baseline-0 Latin against this CJK design.

    Zero for every conventional CJK font (ideograph bottom about 8 % of the box
    below the baseline). A CJK design whose ideographs sit on, or far below,
    the baseline otherwise shows digits visibly low/high next to Han ("36岁").
    """
    glyph_set = base_glyph_set if base_glyph_set is not None else base.getGlyphSet()
    boxes = [box for box in (_bounds_for_codepoint(base, glyph_set, ord(char))
                             for char in CJK_BOX_PROBES) if box and box[3] > box[1]]
    if len(boxes) < 2:
        return 0.0
    bottom = float(statistics.median(box[1] for box in boxes))
    height = float(statistics.median(box[3] - box[1] for box in boxes))
    upem = base["head"].unitsPerEm
    if height < upem * 0.5:
        return 0.0
    ratio = -bottom / height
    if abs(ratio - CJK_BASELINE_RATIO) <= CJK_BASELINE_TOLERANCE:
        return 0.0
    shift = bottom + CJK_BASELINE_RATIO * height
    limit = upem * CJK_BASELINE_SHIFT_LIMIT_RATIO
    return max(-limit, min(limit, shift))


def _cjk_box_height(base: TTFont, glyph_set) -> float | None:
    boxes = [box for box in (_bounds_for_codepoint(base, glyph_set, ord(char))
                             for char in CJK_BOX_PROBES) if box and box[3] > box[1]]
    if len(boxes) < 2:
        return None
    height = float(statistics.median(box[3] - box[1] for box in boxes))
    return height if height >= base["head"].unitsPerEm * 0.5 else None


def cjk_cap_correction(base: TTFont, base_glyph_set=None) -> tuple[float, float]:
    """(size factor, vertical shift) that sizes Latin to the CJK ideographs.

    (1.0, 0.0) for conventional pairings. When the base font's own Latin caps
    are far below 0.88 of its ideograph box, Latin is enlarged to that ratio
    and grows upward from the baseline; growing around the centre dropped the
    digits below the Han they sit beside ("36岁" read low on 花轮丸).
    """
    glyph_set = base_glyph_set if base_glyph_set is not None else base.getGlyphSet()
    cjk_h = _cjk_box_height(base, glyph_set)
    cap = _median_flat_extents(base, glyph_set, "latin")
    if not cjk_h or not cap or cap[1] <= cap[0]:
        return 1.0, 0.0
    cap_h = cap[1] - cap[0]
    if abs(cap_h / cjk_h - CJK_CAP_RATIO) <= CJK_CAP_TOLERANCE:
        return 1.0, 0.0
    lo, hi = CJK_CAP_FACTOR_LIMITS
    factor = max(lo, min(hi, CJK_CAP_RATIO * cjk_h / cap_h))
    if factor == 1.0:
        return 1.0, 0.0
    return factor, 0.0


# Manual fine-tuning chosen in the App (英数大小 / 英数上下位置), whole percent.
# Applied after the automatic alignment; (0, 0) leaves it exactly untouched.
MANUAL_SIZE_LIMITS = (-15, 15)
MANUAL_OFFSET_LIMITS = (-10, 10)


def manual_tune(size_percent=0, offset_percent=0) -> tuple[int, int]:
    """Clamp the App's Latin/digit size and vertical offset to whole percents."""
    def clamp(value, limits):
        try:
            value = int(value or 0)
        except (TypeError, ValueError):
            return 0
        return max(limits[0], min(limits[1], value))
    return clamp(size_percent, MANUAL_SIZE_LIMITS), clamp(offset_percent, MANUAL_OFFSET_LIMITS)


def _role_transform(base: TTFont, src: TTFont, src_glyph_set, role: str,
                    tune: tuple[int, int] = (0, 0)) -> tuple[float, float]:
    scale, shift = _auto_role_transform(base, src, src_glyph_set, role)
    size, offset = manual_tune(*tune)
    if not size and not offset:
        return scale, shift
    upem = base["head"].unitsPerEm
    # Resize around the imported cap centre (like cjk_cap_correction), so a size
    # change does not move Latin/digits up or down; then apply the plain offset
    # (percent of the em, positive = up).
    box = _median_flat_extents(src, src_glyph_set, role)
    centre = ((box[0] + box[1]) / 2.0 * scale + shift) if box and box[1] > box[0] else upem * 0.35
    factor = 1.0 + size / 100.0
    return scale * factor, shift * factor + centre * (1.0 - factor) + upem * offset / 100.0


def _auto_role_transform(base: TTFont, src: TTFont, src_glyph_set, role: str) -> tuple[float, float]:
    base_glyph_set = base.getGlyphSet()
    upem_scale = base["head"].unitsPerEm / src["head"].unitsPerEm
    cjk_shift = cjk_baseline_shift(base, base_glyph_set)
    cap_factor, cap_shift = cjk_cap_correction(base, base_glyph_set)
    base_box = _median_flat_extents(base, base_glyph_set, role)
    src_box = _median_flat_extents(src, src_glyph_set, role)
    if not base_box or not src_box:
        return upem_scale, cjk_shift
    cjk_shift += cap_shift
    ratio = cap_factor * (base_box[1] - base_box[0]) / ((src_box[1] - src_box[0]) * upem_scale)
    scale = upem_scale * max(0.82, min(1.18, ratio))
    # OpenType baseline is y=0. Never inherit the CJK base font's potentially vertically
    # centered ASCII bottom; only correct genuine source-font vertical displacement.
    shift = -src_box[0] * scale
    limit = base["head"].unitsPerEm * BASELINE_SHIFT_LIMIT_RATIO
    return scale, max(-limit, min(limit, shift)) + cjk_shift


def enclose_imported_bounds(font: TTFont, bounds) -> None:
    """Expand cached font boxes to enclose new ink when recalcBBoxes is disabled.

    Preserve the source's enclosing box for untouched and variable glyphs. This
    does not invent a smaller box, alter line metrics, or rescan all CJK outlines.
    """
    if bounds is None:
        return
    box = (math.floor(bounds[0]), math.floor(bounds[1]),
           math.ceil(bounds[2]), math.ceil(bounds[3]))
    head = font['head']
    head.xMin = min(head.xMin, box[0]); head.yMin = min(head.yMin, box[1])
    head.xMax = max(head.xMax, box[2]); head.yMax = max(head.yMax, box[3])
    for tag in ('CFF ', 'CFF2'):
        if tag in font:
            top = font[tag].cff.topDictIndex[0]
            if hasattr(top, 'FontBBox'):
                prior = top.FontBBox
                top.FontBBox = [min(prior[0], box[0]), min(prior[1], box[1]),
                                max(prior[2], box[2]), max(prior[3], box[3])]
