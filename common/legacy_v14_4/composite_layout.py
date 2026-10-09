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
# overshoot the baseline and introduce a systematic upward bias.
FLAT_BOTTOM_PROBES = {"latin": "HIEX", "digit": "147"}
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


def _role_transform(base: TTFont, src: TTFont, src_glyph_set, role: str) -> tuple[float, float]:
    base_glyph_set = base.getGlyphSet()
    probes = tuple(map(ord, "AHIOXEx" if role == "latin" else "0189"))
    upem_scale = base["head"].unitsPerEm / src["head"].unitsPerEm
    pairs: list[tuple[tuple[float, float, float, float], tuple[float, float, float, float]]] = []
    for codepoint in probes:
        base_bounds = _bounds_for_codepoint(base, base_glyph_set, codepoint)
        src_bounds = _bounds_for_codepoint(src, src_glyph_set, codepoint)
        if base_bounds and src_bounds and src_bounds[3] > src_bounds[1] and base_bounds[3] > base_bounds[1]:
            pairs.append((base_bounds, src_bounds))
    if not pairs:
        return upem_scale, 0.0
    ratios = [
        (base_bounds[3] - base_bounds[1]) / ((src_bounds[3] - src_bounds[1]) * upem_scale)
        for base_bounds, src_bounds in pairs
    ]
    shape_scale = max(0.82, min(1.18, float(statistics.median(ratios))))
    scale = upem_scale * shape_scale
    source_bottoms = [
        bounds[1]
        for bounds in (
            _bounds_for_codepoint(src, src_glyph_set, codepoint)
            for codepoint in map(ord, FLAT_BOTTOM_PROBES.get(role, ""))
        )
        if bounds
    ]
    if not source_bottoms:
        return scale, 0.0
    # OpenType baseline is y=0. Never inherit the CJK base font's potentially vertically
    # centered ASCII bottom; only correct genuine source-font vertical displacement.
    shift = -float(statistics.median(source_bottoms)) * scale
    limit = base["head"].unitsPerEm * BASELINE_SHIFT_LIMIT_RATIO
    return scale, max(-limit, min(limit, shift))



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
