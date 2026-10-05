#!/usr/bin/env python3
"""Narrow fixed-text imports into protected, single-weight-axis glyf fonts.

The stock variable font remains the base. Imported text outlines are fixed;
all original glyph IDs, stock advance variations, and other-script outline
variations are retained. This is not a general variable-font conversion.
"""
from __future__ import annotations

import copy
import math

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.ttLib.tables.otTables import NO_VARIATION_INDEX
from fontTools.varLib.builder import buildVarIdxMap
from fontTools.varLib.models import supportScalar
from fontTools.varLib.varStore import VarStoreInstancer

import luoshu_merge


SCALAR_VARIATION_TABLES = ("fvar", "avar", "STAT", "MVAR")
UNSUPPORTED_OUTLINE_TABLES = ("CFF ", "CFF2", "COLR", "SVG ", "CBDT", "EBDT", "sbix")
VARIABLE_SOURCE_TABLES = ("fvar", "gvar", "HVAR", "VVAR", "MVAR", "CFF2")


def _valid_var_index(store, index: int) -> bool:
    if index == NO_VARIATION_INDEX:
        return True
    if not isinstance(index, int) or not 0 <= index <= 0xFFFFFFFF:
        return False
    outer, inner = index >> 16, index & 0xFFFF
    data = getattr(store, "VarData", [])
    return outer < len(data) and inner < len(getattr(data[outer], "Item", []))


def _phantom_variations(font: TTFont) -> dict[str, list[tuple[dict, list]]]:
    """Resolve metric deltas against the ORIGINAL stock point topology."""
    from fontTools.varLib.iup import iup_delta
    glyf = font["glyf"]
    vertical_metrics = font["vmtx"].metrics if "vmtx" in font else None
    result = {}
    for name, variations in font["gvar"].variations.items():
        metric_variations = []
        for variation in variations:
            if set(variation.axes) - {"wght"} or len(variation.coordinates) < 4:
                raise luoshu_merge.MergeError("partial-stock-variable-unsupported")
            coordinates, control = glyf._getCoordinatesAndControls(
                name, font["hmtx"].metrics, vertical_metrics)
            if len(coordinates) != len(variation.coordinates):
                raise luoshu_merge.MergeError("partial-stock-variable-metrics-unsupported")
            deltas = variation.coordinates
            if any(delta is None for delta in deltas[-4:]):
                ends = control.endPts if control.numberOfContours >= 1 \
                    else list(range(len(control.endPts)))
                deltas = iup_delta(deltas, coordinates, ends)
            phantoms = [tuple(delta) for delta in deltas[-4:]]
            # A fixed outline's xMin must equal its left side bearing for a
            # TrueType variable font. Nonzero left phantom variation would
            # violate this after importing fixed outlines. Vertical advance
            # variation remains outside this narrow adapter too.
            if phantoms[0] != (0, 0) or any(delta != (0, 0) for delta in phantoms[-2:]):
                raise luoshu_merge.MergeError("partial-stock-variable-metrics-unsupported")
            metric_variations.append((dict(variation.axes), phantoms))
        result[name] = metric_variations
    return result


def _consistent_advances(font: TTFont, phantoms: dict) -> bool:
    """Prove HVAR and gvar give the same advances over the single axis.

    Both representations are piecewise linear. Their union of support
    breakpoints therefore proves equality throughout the normalized range,
    rather than checking only the common user weights.
    """
    hvar = font["HVAR"].table
    locations = {-1.0, 0.0, 1.0}
    for region in hvar.VarStore.VarRegionList.Region:
        axis = region.VarRegionAxis[0]
        locations.update((axis.StartCoord, axis.PeakCoord, axis.EndCoord))
    for variations in phantoms.values():
        for axes, _coordinates in variations:
            if "wght" in axes:
                locations.update(axes["wght"])
    if not all(math.isfinite(value) and -1 <= value <= 1 for value in locations):
        return False
    indexes = {name: index for index, name in enumerate(font.getGlyphOrder())} \
        if hvar.AdvWidthMap is None else hvar.AdvWidthMap.mapping
    instancer = VarStoreInstancer(hvar.VarStore, font["fvar"].axes)
    for location in locations:
        normalized = {"wght": location}
        instancer.setLocation(normalized)
        for name in font.getGlyphOrder():
            gvar_delta = sum(supportScalar(normalized, axes) * (values[1][0] - values[0][0])
                             for axes, values in phantoms.get(name, []))
            if abs(gvar_delta - instancer[indexes[name]]) > 0.000001:
                return False
    return True


def validate_variable_base(font: TTFont) -> str:
    """Return an explicit kept-stock reason, or ``""`` for this narrow case.

    HVAR layout and gvar rasterizer metrics must agree throughout the axis.
    Imported glyphs receive new zero outline deltas and the original metric
    phantom deltas, while keeping their original HVAR mapping. Explicit
    bearing maps, variable vertical metrics and other axes remain unsupported.
    """
    try:
        if "glyf" not in font or not all(tag in font for tag in ("fvar", "gvar", "HVAR")) \
                or any(tag in font for tag in UNSUPPORTED_OUTLINE_TABLES):
            return "partial-stock-variable-unsupported"
        axes = font["fvar"].axes
        if len(axes) != 1 or axes[0].axisTag != "wght":
            return "partial-stock-variable-unsupported"
        axis = axes[0]
        values = (axis.minValue, axis.defaultValue, axis.maxValue)
        if not all(math.isfinite(value) for value in values) \
                or not axis.minValue <= axis.defaultValue <= axis.maxValue \
                or axis.minValue == axis.maxValue:
            return "partial-stock-variable-unsupported"
        if "VVAR" in font:
            return "partial-stock-variable-metrics-unsupported"
        if not font["head"].flags & 2:
            return "partial-stock-variable-metrics-unsupported"
        if luoshu_merge.partial_point_layout(font):
            return "partial-stock-point-layout-unsupported"
        order = font.getGlyphOrder()
        hvar = font["HVAR"].table
        if hvar.LsbMap is not None or hvar.RsbMap is not None:
            return "partial-stock-variable-metrics-unsupported"
        store = hvar.VarStore
        if store.Format != 1 or store.VarRegionList.RegionAxisCount != 1:
            return "partial-stock-variable-metrics-unsupported"
        for field in ("AdvWidthMap", "LsbMap", "RsbMap"):
            mapping = getattr(hvar, field, None)
            if mapping is None:
                indexes = range(len(order)) if field == "AdvWidthMap" else ()
            else:
                if not set(order) <= mapping.mapping.keys():
                    return "partial-stock-variable-metrics-unsupported"
                indexes = (mapping.mapping[name] for name in order)
            if not all(_valid_var_index(store, index) for index in indexes):
                return "partial-stock-variable-metrics-unsupported"
        phantoms = _phantom_variations(font)
        if not _consistent_advances(font, phantoms):
            return "partial-stock-variable-metrics-unsupported"
    except luoshu_merge.MergeError as error:
        return str(error)
    except Exception:
        return "partial-stock-variable-unreadable"
    return ""


def _scalar_table_bytes(font: TTFont) -> dict[str, bytes]:
    reader = getattr(font, "reader", None)
    return {tag: reader[tag] if reader is not None and tag in reader else font[tag].compile(font)
            for tag in SCALAR_VARIATION_TABLES if tag in font}


def import_variable_partial(base: TTFont, sources: dict[str, TTFont]) -> dict:
    """Import fully instantiated text sources while retaining stock variation.

    The caller must discard the in-memory candidate on any exception. It is
    responsible for preserving original layout serialization and for staging
    the final font atomically, as with a static partial import.
    """
    reason = validate_variable_base(base)
    if reason:
        raise luoshu_merge.MergeError(reason)
    if any(tag in source for source in sources.values() for tag in VARIABLE_SOURCE_TABLES):
        raise luoshu_merge.MergeError("partial-source-variable-not-fixed")
    original_order = list(base.getGlyphOrder())
    original_metrics = dict(base["hmtx"].metrics)
    original_phantoms = _phantom_variations(base)
    scalar_bytes = _scalar_table_bytes(base)
    held = {tag: base[tag] for tag in ("fvar", "gvar", "HVAR")}
    for tag in held:
        del base[tag]
    try:
        details = luoshu_merge.import_partial_text(base, sources)
    finally:
        for tag, table in held.items():
            base[tag] = table
    changed = details.get("replacedGlyphNames")
    clones = details.get("clonedGlyphSources")
    if not isinstance(changed, list) or not isinstance(clones, dict) \
            or set(base.getGlyphOrder()) - set(original_order) != set(clones) \
            or not set(changed) <= set(original_order) \
            or any(original not in original_metrics for original in clones.values()):
        raise luoshu_merge.MergeError("partial-stock-variable-import-unproved")
    if base.getGlyphOrder()[:len(original_order)] != original_order \
            or any(base["hmtx"].metrics[name][0] != original_metrics[name][0]
                   for name in original_order):
        raise luoshu_merge.MergeError("partial-stock-variable-advance-changed")
    gvar = base["gvar"].variations
    # Copy original deltas before clearing changed glyphs: retained composites
    # now reference these hidden copies and still need their complete original
    # outline and phantom variations, including original point order.
    for clone, original in clones.items():
        gvar[clone] = copy.deepcopy(gvar.get(original, []))
    for name in changed:
        glyph = base["glyf"][name]
        points = len(glyph.getCoordinates(base["glyf"])[0])
        gvar[name] = [TupleVariation(axes, [(0, 0)] * points + phantoms)
                      for axes, phantoms in original_phantoms.get(name, [])
                      if any(delta != (0, 0) for delta in phantoms)]
    hvar = base["HVAR"].table
    if clones and hvar.AdvWidthMap is None:
        # A null map means outer=0, inner=original GID. Newly appended GIDs
        # must explicitly reuse the original glyph's index, not their own GID.
        hvar.AdvWidthMap = buildVarIdxMap(range(len(original_order)), original_order)
    for field in ("AdvWidthMap", "LsbMap", "RsbMap"):
        mapping = getattr(hvar, field, None)
        if mapping is not None:
            for clone, original in clones.items():
                mapping.mapping[clone] = mapping.mapping[original]
    # The objects remain usable (gvar compilation needs fvar.axes), while
    # their unchanged original byte serialization is emitted verbatim. This
    # also avoids normalizing unknown optional fields in STAT/MVAR/avar.
    for tag, data in scalar_bytes.items():
        base[tag].compile = lambda _font, raw=data: raw
    axis = base["fvar"].axes[0]
    details.update({
        "stockVariable": True,
        "variationPolicy": "fixed-user-outlines; stock-advance-variation-retained",
        "preservedVariationTables": [tag for tag in (*SCALAR_VARIATION_TABLES, "gvar", "HVAR") if tag in base],
        "preservedStockAxes": [{"tag": axis.axisTag, "minimum": axis.minValue,
                                "default": axis.defaultValue, "maximum": axis.maxValue}],
        "clonedVariationGlyphs": len(clones),
        "staticImportedVariableGlyphs": len(changed),
        "importedMetricPhantomVariations": sum(len(gvar[name]) for name in changed),
        "originalHvarMappingsPreserved": True,
        "verticalAdvancePolicy": "retain-stock-constant; variable-vertical-unsupported",
    })
    return details
