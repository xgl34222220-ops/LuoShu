#!/usr/bin/env python3
"""Copy Latin and digit glyphs into a CJK base font (engine v3 composite).

Ported from the legacy composite builder that shipped on devices: the CJK font
stays the complete base, Latin and digit outlines are drawn into glyph slots
that already exist in the base, scaled to the base cap height and moved onto
the baseline. The output keeps one complete cmap.
"""
from __future__ import annotations

import math
import copy
import statistics
import unicodedata
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
    | set(range(0xFF21, 0xFF3B))  # Fullwidth Latin letters are the English slot.
    | set(range(0xFF41, 0xFF5B))
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


def _draw(glyph_set, name: str, pen, scale: float, shift: float,
          x_scale: float | None = None, x_shift: float = 0.0) -> None:
    recorder = DecomposingRecordingPen(glyph_set)
    glyph_set[name].draw(recorder)
    recorder.replay(TransformPen(pen, (scale if x_scale is None else x_scale, 0, 0, scale, x_shift, shift)))


def _replace_glyf(base: TTFont, src_kind: str, glyph_set, base_name: str, src_name: str,
                  scale: float, shift: float, x_scale: float | None = None, x_shift: float = 0.0) -> None:
    pen = TTGlyphPen(None)
    _draw(glyph_set, src_name, Cu2QuPen(pen, max_err=max(0.5, base["head"].unitsPerEm / 2000),
                                        reverse_direction=src_kind in {"cff", "cff2"}), scale, shift, x_scale, x_shift)
    glyph = pen.glyph()
    base["glyf"][base_name] = glyph
    glyph.recalcBounds(base["glyf"])
    if not hasattr(glyph, "xMin"):
        glyph.xMin = glyph.yMin = glyph.xMax = glyph.yMax = 0
    _enclose_bounds(base, (glyph.xMin, glyph.yMin, glyph.xMax, glyph.yMax))
    if "gvar" in base:
        base["gvar"].variations.pop(base_name, None)


def _replace_cff(base: TTFont, src_kind: str, glyph_set, base_name: str, src_name: str,
                 scale: float, shift: float, width: int,
                 x_scale: float | None = None, x_shift: float = 0.0) -> None:
    tag = "CFF " if "CFF " in base else "CFF2"
    cff = base[tag].cff
    top = cff.topDictIndex[0]
    _old, selector = top.CharStrings.getItemAndSelector(base_name)
    private = top.FDArray[selector or 0].Private if hasattr(top, "FDArray") else top.Private
    is_cff2 = tag == "CFF2"
    pen = T2CharStringPen(None if is_cff2 else width, None, CFF2=is_cff2)
    _draw(glyph_set, src_name, Qu2CuPen(pen, max_err=max(0.5, base["head"].unitsPerEm / 2000),
                                        all_cubic=True, reverse_direction=src_kind == "glyf"), scale, shift, x_scale, x_shift)
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


# A protected system text face keeps its scripts and symbols. This deliberately
# excludes combining marks, currencies and the letterlike-symbol range used by
# the full composite importer.
PARTIAL_TEXT_CODEPOINTS = frozenset(
    {point for span in (range(0x41, 0x7B), range(0xC0, 0x250), range(0x1E00, 0x1F00),
                       range(0xFB00, 0xFB07), range(0xFF21, 0xFF5B)) for point in span
     if unicodedata.category(chr(point)).startswith("L")
     and "LATIN" in unicodedata.name(chr(point), "")}
    | set(range(0x30, 0x3A)) | set(range(0xFF10, 0xFF1A))
    | set(map(ord, " !\"'(),-./:;?_"))
)


def _unicode_aliases(font: TTFont) -> dict[str, set[int]]:
    aliases: dict[str, set[int]] = {}
    for table in font["cmap"].tables:
        if table.isUnicode():
            for point, name in (getattr(table, "cmap", None) or {}).items():
                aliases.setdefault(name, set()).add(point)
        # A UVS non-default mapping also owns the glyph, even when getBestCmap
        # does not expose it. Protect it rather than inferring its semantics.
        if table.format == 14:
            for pairs in (getattr(table, "uvsDict", None) or {}).values():
                for point, name in pairs:
                    if name is not None:
                        aliases.setdefault(name, set()).add(-1)
    return aliases


def _gsub_tables(font: TTFont):
    if "GSUB" not in font or font["GSUB"].table.LookupList is None:
        return
    for lookup in font["GSUB"].table.LookupList.Lookup:
        for table in lookup.SubTable:
            yield table.ExtSubTable if lookup.LookupType == 7 else table


def partial_point_layout(font: TTFont) -> bool:
    """Point-index anchors cannot be retained on a newly drawn target glyph.

    Fail closed for the whole partial face rather than guessing which nested
    coverage associates an AnchorFormat2/GDEF point reference with a target.
    """
    seen: set[int] = set()
    def visit(value) -> bool:
        if isinstance(value, (str, int, float, bytes, type(None))) or id(value) in seen:
            return False
        seen.add(id(value))
        if any(hasattr(value, field) for field in ("AnchorPoint", "CaretValuePoint", "PointIndex", "BaseCoordPoint")):
            return True
        children = value.values() if isinstance(value, dict) else value \
            if isinstance(value, (list, tuple)) else vars(value).values() if hasattr(value, "__dict__") else []
        return any(visit(child) for child in children)
    return any(visit(font[tag].table) for tag in ("GPOS", "GDEF", "BASE") if tag in font)


def partial_ligatures(font: TTFont) -> dict[tuple[int, ...], str]:
    """Unambiguous Latin ligatures, keyed by the Unicode input sequence.

    A common sequence with several feature-specific outputs is kept stock;
    matching an arbitrary stylistic alternative would misidentify the glyph.
    """
    aliases = _unicode_aliases(font)
    inputs = {name: next(iter(points)) for name, points in aliases.items()
              if len(points) == 1 and points <= PARTIAL_TEXT_CODEPOINTS}
    choices: dict[tuple[int, ...], set[str]] = {}
    for table in _gsub_tables(font):
        for first, ligatures in (getattr(table, "ligatures", None) or {}).items():
            for ligature in ligatures:
                names = [first, *ligature.Component]
                if all(name in inputs for name in names) \
                        and not aliases.get(ligature.LigGlyph, set()) - PARTIAL_TEXT_CODEPOINTS:
                    sequence = tuple(inputs[name] for name in names)
                    # Punctuation/numerals do not prove a text ligature.
                    if all(unicodedata.category(chr(point)).startswith("L") for point in sequence):
                        choices.setdefault(sequence, set()).add(ligature.LigGlyph)
    return {sequence: next(iter(names)) for sequence, names in choices.items() if len(names) == 1}


def _partial_layout_protected(font: TTFont, plans: dict[str, tuple[str, str]],
                              source_ligatures: dict[tuple[int, ...], str]) -> set[str]:
    """Protect outputs with any unproved producer, including contextual calls."""
    if "GSUB" not in font or font["GSUB"].table.LookupList is None:
        return set()
    lookups = font["GSUB"].table.LookupList.Lookup
    referenced: set[int] = set()
    seen: set[int] = set()
    def visit(value):
        if isinstance(value, (str, int, float, bytes, type(None))):
            return
        if id(value) in seen:
            return
        seen.add(id(value))
        if value.__class__.__name__ == "SubstLookupRecord" and hasattr(value, "LookupListIndex"):
            referenced.add(int(value.LookupListIndex))
        for item in value if isinstance(value, (list, tuple)) else vars(value).values() \
                if hasattr(value, "__dict__") else []:
            visit(item)
    visit(font["GSUB"].table)
    aliases = _unicode_aliases(font)
    inputs = {name: next(iter(points)) for name, points in aliases.items()
              if len(points) == 1 and points <= PARTIAL_TEXT_CODEPOINTS}
    protected: set[str] = set()
    rules = []
    for index, lookup in enumerate(lookups):
        for subtable in lookup.SubTable:
            table = subtable.ExtSubTable if lookup.LookupType == 7 else subtable
            emitted = set()
            for output in (getattr(table, "mapping", None) or {}).values():
                emitted.update([output] if isinstance(output, str) else output)
            for outputs in (getattr(table, "alternates", None) or {}).values():
                emitted.update(outputs)
            emitted.update(getattr(table, "Substitute", None) or [])
            protected.update(emitted & plans.keys())
            for first, ligatures in (getattr(table, "ligatures", None) or {}).items():
                for ligature in ligatures:
                    names = [first, *ligature.Component]
                    sequence = tuple(inputs[name] for name in names) if all(name in inputs for name in names) else ()
                    safe = bool(sequence) and index not in referenced \
                        and all(unicodedata.category(chr(point)).startswith("L") for point in sequence) \
                        and plans.get(ligature.LigGlyph) == ("latin", source_ligatures.get(sequence))
                    rules.append((names, ligature.LigGlyph, safe))
    # A ligature fed by an unproved substitution is unproved too.
    while True:
        added = {output for names, output, safe in rules
                 if output in plans and (not safe or any(name in protected for name in names))}
        if added <= protected:
            break
        protected.update(added)
    return protected


def import_partial_text(base: TTFont, sources: dict[str, TTFont]) -> dict:
    """Replace only proved text glyphs in a static stock face, preserving cells.

    Existing glyph IDs, cmap and layout tables stay in place. A shared Unicode
    alias protects a glyph. Original component glyphs get hidden copies so
    retained composite outlines, point order and instructions stay unchanged.
    """
    if "glyf" not in base or any(tag in base for tag in ("fvar", "gvar", "HVAR", "VVAR", "CFF2")):
        raise MergeError("保护字体的局部替换只支持静态原厂基底")
    if partial_point_layout(base):
        raise MergeError("保护字体含字形点索引定位，不能安全局部替换")
    for role, source in sources.items():
        if not REQUIRED[role] <= (source.getBestCmap() or {}).keys():
            raise MergeError(f"保护字体局部替换的{role}源缺少必要字符")
    aliases = _unicode_aliases(base)
    cmap = base.getBestCmap() or {}
    plans: dict[str, tuple[str, str]] = {}
    for point in sorted(PARTIAL_TEXT_CODEPOINTS):
        role = "digit" if point in DIGIT_CODEPOINTS else "latin"
        source_cmap = sources[role].getBestCmap() or {}
        name, source_name = cmap.get(point), source_cmap.get(point)
        if name and source_name:
            prior = plans.get(name)
            item = (role, source_name)
            # Different source aliases for one base glyph are ambiguous.
            if prior is None or prior == item:
                plans[name] = item
            else:
                aliases.setdefault(name, set()).add(-1)
    base_ligatures = partial_ligatures(base)
    source_ligatures = partial_ligatures(sources["latin"])
    for sequence, name in base_ligatures.items():
        if sequence in source_ligatures:
            item = ("latin", source_ligatures[sequence])
            if name in plans and plans[name] != item:
                aliases.setdefault(name, set()).add(-1)
            else:
                plans[name] = item
    protected = {name for name in plans if aliases.get(name, set()) - PARTIAL_TEXT_CODEPOINTS}
    layout_protected = _partial_layout_protected(base, plans, source_ligatures)
    protected.update(layout_protected)
    # Composite USE_MY_METRICS advances can come from a component rather
    # than this glyph's own hmtx/HVAR. Redrawing it as a simple glyph would
    # silently change FreeType/Android advances even when hmtx is retained.
    metric_protected = {name for name in plans if base["glyf"][name].isComposite()
                        and any(component.flags & 0x0200 for component in base["glyf"][name].components)}
    protected.update(metric_protected)
    clone_names: dict[str, str] = {}
    # Retained composites must keep the original component outlines. Append
    # private copies without moving any original glyph ID; this also keeps
    # AnchorFormat2 point indices and composite hint instructions intact.
    if "glyf" in base:
        order = list(base.getGlyphOrder())
        changed = plans.keys() - protected
        needed = {component.glyphName for name in order if base["glyf"][name].isComposite()
                  for component in base["glyf"][name].components if component.glyphName in changed}
        for name in sorted(needed):
            clone = f"luoshu.stock.{name}"
            while clone in base["glyf"]:
                clone += ".copy"
            clone_names[name] = clone
            base["glyf"][clone] = copy.deepcopy(base["glyf"][name])
            base["hmtx"].metrics[clone] = base["hmtx"].metrics[name]
            if "vmtx" in base:
                base["vmtx"].metrics[clone] = base["vmtx"].metrics[name]
            order.append(clone)
        base.setGlyphOrder(order)
        for name in order:
            glyph = base["glyf"][name]
            if glyph.isComposite():
                for component in glyph.components:
                    component.glyphName = clone_names.get(component.glyphName, component.glyphName)
    counts = {"latin": 0, "digit": 0, "ligatures": 0}
    glyph_sets = {role: font.getGlyphSet() for role, font in sources.items()}
    transforms = {role: _role_transform(base, font, glyph_sets[role], role)
                  for role, font in sources.items()}
    ligature_names = set(base_ligatures.values())
    for name, (role, source_name) in sorted(plans.items()):
        if name in protected:
            continue
        source = sources[role]
        glyph_set = glyph_sets[role]
        scale, shift = transforms[role]
        advance, old_lsb = base["hmtx"].metrics[name]
        pen = BoundsPen(glyph_set)
        glyph_set[source_name].draw(pen)
        x_scale, x_shift = scale, 0.0
        if pen.bounds is not None:
            left, _bottom, right, _top = pen.bounds
            # Keep the original cell advance, including a monospace cell. Fit
            # a wide user glyph horizontally and center it within that cell.
            if advance > 0 and right > left:
                x_scale = min(scale, advance / (right - left))
                x_shift = (advance - (right - left) * x_scale) / 2 - left * x_scale
        if outline_kind(base) == "glyf":
            _replace_glyf(base, outline_kind(source), glyph_set, name, source_name,
                          scale, shift, x_scale, x_shift)
            lsb = base["glyf"][name].xMin if pen.bounds is not None else old_lsb
            glyph = base["glyf"][name]
            if base["maxp"].tableVersion == 0x10000:
                base["maxp"].maxPoints = max(base["maxp"].maxPoints, len(glyph.coordinates))
                base["maxp"].maxContours = max(base["maxp"].maxContours, glyph.numberOfContours)
        else:
            _replace_cff(base, outline_kind(source), glyph_set, name, source_name,
                         scale, shift, advance, x_scale, x_shift)
            lsb = int(round(pen.bounds[0] * x_scale + x_shift)) if pen.bounds else old_lsb
        base["hmtx"].metrics[name] = (advance, lsb)
        counts[role] += 1
        counts["ligatures"] += int(name in ligature_names)
    return {"latinGlyphsReplaced": counts["latin"], "digitGlyphsReplaced": counts["digit"],
            "asciiLettersBefore": sum(point in cmap for point in REQUIRED["latin"]),
            "asciiDigitsBefore": sum(point in cmap for point in REQUIRED["digit"]),
            "asciiLettersReplaced": sum(cmap.get(point) in plans and cmap.get(point) not in protected
                                        for point in REQUIRED["latin"]),
            "asciiDigitsReplaced": sum(cmap.get(point) in plans and cmap.get(point) not in protected
                                       for point in REQUIRED["digit"]),
            "ligatureGlyphsReplaced": counts["ligatures"],
            "protectedSharedGlyphs": sorted(protected),
            "protectedLayoutGlyphs": sorted(layout_protected),
            "protectedMetricGlyphs": sorted(metric_protected),
            "retainedComponentClones": len(clone_names),
            "clonedGlyphCount": len(clone_names), "originalGlyphOrderPreservedPrefix": True,
            "clonedGlyphSources": {clone: name for name, clone in clone_names.items()},
            "replacedGlyphNames": sorted(plans.keys() - protected),
            "preservedLigatureGlyphs": sorted(ligature_names - (plans.keys() - protected)),
            "layoutCoverage": "matched-latin-ligatures; other substitutions retain stock",
            "advancePolicy": "retain-stock-cell"}


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
