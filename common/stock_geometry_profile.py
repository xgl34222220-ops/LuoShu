#!/usr/bin/env python3
"""Bounded scan-time OEM glyph measurements, sealed to source bytes and face.

The archive contains measurements, never substituted outlines. Source-view
provenance is separately verified by stock_font_provenance on capture/use.
"""
from __future__ import annotations
import hashlib
from pathlib import Path
from typing import Any
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
import device_font_template as template_engine

SCHEMA = "stock-geometry-profile-v1"

class GeometryIdentityError(ValueError):
    """Measured bytes or face do not match the scan identity; capture must stop."""
    pass

def profile_from_font(font: TTFont) -> dict[str, Any]:
    if "head" not in font or "hhea" not in font:
        raise ValueError("字体缺少 head/hhea")
    head = font["head"]
    hhea = font["hhea"]
    os2 = font["OS/2"] if "OS/2" in font else None
    metrics: dict[str, Any] = {
        "unitsPerEm": int(head.unitsPerEm),
        "headYMin": int(getattr(head, "yMin", 0)),
        "headYMax": int(getattr(head, "yMax", 0)),
        "hheaAscent": int(hhea.ascent),
        "hheaDescent": int(hhea.descent),
        "hheaLineGap": int(hhea.lineGap),
        "typoAscender": int(getattr(os2, "sTypoAscender", 0)) if os2 else None,
        "typoDescender": int(getattr(os2, "sTypoDescender", 0)) if os2 else None,
        "typoLineGap": int(getattr(os2, "sTypoLineGap", 0)) if os2 else None,
        "winAscent": int(getattr(os2, "usWinAscent", 0)) if os2 else None,
        "winDescent": int(getattr(os2, "usWinDescent", 0)) if os2 else None,
        "capHeight": int(getattr(os2, "sCapHeight", 0)) if os2 and hasattr(os2, "sCapHeight") else None,
        "xHeight": int(getattr(os2, "sxHeight", 0)) if os2 and hasattr(os2, "sxHeight") else None,
        "weightClass": int(getattr(os2, "usWeightClass", 400)) if os2 else 400,
        "widthClass": int(getattr(os2, "usWidthClass", 5)) if os2 else 5,
        "fsSelection": int(getattr(os2, "fsSelection", 0)) if os2 else 0,
    }
    return {
        "path": "",
        "faceIndex": -1,
        "names": sorted(template_engine.font_names(font)),
        "metrics": metrics,
        "probeSchema": template_engine.PROBE_SCHEMA,
        "probes": {
            name: template_engine.glyph_group(font, points)
            for name, points in template_engine.PROBE_GROUPS.items()
        },
    }

def _digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def capture_geometry_profile(path: Path, face_index: int, identity: dict[str, Any]) -> dict[str, Any]:
    path = Path(path)
    expected = str(identity.get("sha256") or "")
    if len(expected) != 64 or int(identity.get("faceIndex", -1)) != int(face_index):
        raise GeometryIdentityError("stock geometry requires a sealed source identity and face")
    if _digest(path) != expected:
        raise GeometryIdentityError("stock changed before geometry capture")
    with path.open("rb") as stream:
        collection = stream.read(4) == b"ttcf"
    if not collection and face_index != 0:
        raise GeometryIdentityError("standalone stock font has no requested face")
    options = dict(lazy=True, recalcTimestamp=False, recalcBBoxes=False)
    if collection:
        options["fontNumber"] = int(face_index)
    font = TTFont(str(path), **options)
    try:
        location = {str(axis.axisTag): float(axis.defaultValue) for axis in font["fvar"].axes} if "fvar" in font else {}
        if location:
            # Default-axis archive is precise; non-default route measurements
            # remain compiler work. Subsetting is measurement-only, never saved.
            if "glyf" in font and "VARC" not in font:
                from fontTools import subset
                opts = subset.Options()
                opts.recalc_bounds = False
                opts.recalc_timestamp = False
                opts.hinting = False
                opts.layout_features = []
                opts.name_IDs = ["*"]
                opts.name_languages = ["*"]
                opts.name_legacy = True
                opts.notdef_outline = True
                opts.drop_tables += [tag for tag in ("GSUB", "GPOS", "GDEF", "BASE", "JSTF", "MATH") if tag not in opts.drop_tables]
                subsetter = subset.Subsetter(options=opts)
                subsetter.populate(unicodes={cp for group in template_engine.PROBE_GROUPS.values() for cp in group})
                subsetter.subset(font)
            # Unsupported variation engines must not make an unmeasured archive.
            if "VARC" in font:
                raise ValueError("VARC scan-time geometry unsupported")
            instantiateVariableFont(font, location, inplace=True, optimize=True)
        profile = profile_from_font(font)
    finally:
        font.close()
    if _digest(path) != expected:
        raise GeometryIdentityError("stock changed during geometry capture")
    return dict(schema=SCHEMA, stockSha256=expected, faceIndex=int(face_index),
                location=location, profile=profile)
