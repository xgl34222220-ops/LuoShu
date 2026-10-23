#!/usr/bin/env python3
"""Make sure a font maps U+0020 SPACE and U+2005 FOUR-PER-EM SPACE.

Some system text stacks (line breaking, justification, number formatting)
ask the active font for U+0020 and U+2005 directly.  When a user font lacks
them the renderer falls back to another font for a single blank, which shows
up as uneven gaps.  This module fills only what is missing:

* A codepoint that is already in the font's best Unicode cmap is never
  touched.  If nothing is missing no table is modified, so saving the font
  gives the same bytes as before.
* A missing codepoint first reuses an existing blank glyph with a fitting
  advance (U+00A0 NO-BREAK SPACE for U+0020; a blank glyph one quarter em wide
  for U+2005, per the Unicode definition of FOUR-PER-EM SPACE).
* Otherwise a new empty glyph is appended at the end of the glyph order, so no
  existing glyph id moves.  TrueType (glyf), CFF and CID-keyed CFF outlines
  are supported.  Variable fonts and CFF2 are only patched by reuse, because
  appending a glyph there would also require consistent gvar/HVAR/VVAR data.

All preconditions are checked before the first table is changed.  When a
precondition fails the font is left untouched and the report says
``skipped``; callers keep building with the original font.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTCollection, TTFont

SCHEMA = "font-space-compat-v1"
SPACE = 0x0020
NBSP = 0x00A0
FOUR_PER_EM_SPACE = 0x2005
TARGETS = (SPACE, FOUR_PER_EM_SPACE)
# cmap subtables that can carry a Unicode BMP mapping and that fontTools
# recompiles safely after adding an entry.
WRITABLE_CMAP_FORMATS = (4, 12)
MAX_CID = 65535
# maxp.numGlyphs is uint16, so glyph ids 0..65534 at most.
MAX_GLYPHS = 65535


class _Skip(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _unicode_subtables(font: TTFont) -> list[Any]:
    if "cmap" not in font:
        return []
    return [table for table in font["cmap"].tables if table.isUnicode() and table.format != 14]


def _is_blank(glyph_set: Any, name: str) -> bool:
    pen = BoundsPen(glyph_set)
    try:
        glyph_set[name].draw(pen)
    except Exception:
        return False
    return pen.bounds is None


def _outline_kind(font: TTFont) -> str:
    if "glyf" in font and "loca" in font:
        return "glyf"
    if "CFF " in font:
        top = font["CFF "].cff.topDictIndex[0]
        return "cid" if hasattr(top, "ROS") else "cff"
    if "CFF2" in font:
        return "cff2"
    return "none"


def _quarter_em(font: TTFont) -> int:
    return max(1, int(round(font["head"].unitsPerEm / 4.0)))


def _fixed_pitch_width(font: TTFont) -> int | None:
    if "post" not in font or not getattr(font["post"], "isFixedPitch", 0):
        return None
    widths = Counter(advance for advance, _ in font["hmtx"].metrics.values() if advance > 0)
    return widths.most_common(1)[0][0] if widths else None


def _unique_name(font: TTFont, preferred: list[str]) -> str:
    existing = set(font.getGlyphOrder())
    for name in preferred:
        if name not in existing:
            return name
    base = preferred[-1]
    serial = 1
    while f"{base}.{serial}" in existing:
        serial += 1
    return f"{base}.{serial}"


def _append_glyph(font: TTFont, kind: str, codepoint: int, width: int) -> str:
    order = list(font.getGlyphOrder())
    if len(order) >= MAX_GLYPHS:
        raise _Skip("glyph_limit")
    if kind == "cid":
        top = font["CFF "].cff.topDictIndex[0]
        used = []
        for name in order:
            try:
                used.append(int(name[3:]) if name.startswith("cid") else 0)
            except ValueError:
                used.append(0)
        cid = max(used, default=0) + 1
        if cid > MAX_CID:
            raise _Skip("cid_exhausted")
        name = f"cid{cid:05d}"
    else:
        name = _unique_name(font, ["space" if codepoint == SPACE else f"uni{codepoint:04X}", f"uni{codepoint:04X}"])

    if kind == "glyf":
        from fontTools.ttLib.tables._g_l_y_f import Glyph

        glyf = font["glyf"]
        order.append(name)
        font.setGlyphOrder(order)
        glyf.glyphOrder = order
        glyf.glyphs[name] = Glyph()
    else:
        from fontTools.misc.psCharStrings import T2CharString

        cff = font["CFF "].cff
        top = cff.topDictIndex[0]
        if kind == "cid":
            fd_index = top.FDSelect[0] if len(top.FDSelect) else 0
            private = top.FDArray[fd_index].Private
        else:
            fd_index = None
            private = top.Private
        default_width = getattr(private, "defaultWidthX", 0)
        nominal_width = getattr(private, "nominalWidthX", 0)
        program: list[Any] = [] if width == default_width else [width - nominal_width]
        program.append("endchar")
        charstrings = top.CharStrings
        charstring = T2CharString(program=program, private=private, globalSubrs=cff.GlobalSubrs)
        if charstrings.charStringsAreIndexed:
            charstrings.charStringsIndex.append(charstring)
            charstrings.charStrings[name] = len(charstrings.charStringsIndex) - 1
        else:
            charstrings.charStrings[name] = charstring
        if fd_index is not None:
            top.FDSelect.append(fd_index)
            cid = int(name[3:])
            if getattr(top, "CIDCount", 8720) <= cid:
                top.CIDCount = cid + 1
        order.append(name)
        top.charset = order
        font.setGlyphOrder(order)

    font["hmtx"].metrics[name] = (width, 0)
    if "vmtx" in font:
        vmtx = font["vmtx"].metrics
        reference = vmtx.get(order[0]) or (font["head"].unitsPerEm, 0)
        vmtx[name] = (reference[0], 0)
    return name


def _map(font: TTFont, codepoint: int, name: str, subtables: list[Any]) -> None:
    for table in subtables:
        table.cmap[codepoint] = name


def _update_os2(font: TTFont, codepoints: list[int]) -> None:
    if "OS/2" not in font or not codepoints:
        return
    os2 = font["OS/2"]
    low, high = min(codepoints), max(codepoints)
    if hasattr(os2, "usFirstCharIndex") and low < os2.usFirstCharIndex:
        os2.usFirstCharIndex = low
    if hasattr(os2, "usLastCharIndex") and high > os2.usLastCharIndex and high <= 0xFFFF:
        os2.usLastCharIndex = high
    if hasattr(os2, "ulUnicodeRange1"):
        if SPACE in codepoints:
            os2.ulUnicodeRange1 |= 1 << 0  # Basic Latin
        if FOUR_PER_EM_SPACE in codepoints:
            os2.ulUnicodeRange1 |= 1 << 31  # General Punctuation


def ensure_space_glyphs(font: TTFont) -> dict[str, Any]:
    """Fill missing U+0020 / U+2005 mappings in ``font`` in place.

    Returns a JSON-serialisable report.  ``status`` is one of ``unchanged``,
    ``patched``, ``partial`` (some codepoint could not be filled) or
    ``skipped`` (font left untouched).
    """
    report: dict[str, Any] = {"schema": SCHEMA, "status": "unchanged", "reused": {}, "added": {}, "unresolved": {}}
    try:
        best = font.getBestCmap() if "cmap" in font else None
    except Exception:
        best = None
    if not best:
        report.update(status="skipped", reason="no_unicode_cmap")
        return report
    missing = [cp for cp in TARGETS if cp not in best]
    report["missing"] = [f"U+{cp:04X}" for cp in missing]
    if not missing:
        return report

    try:
        if "hmtx" not in font or "head" not in font:
            raise _Skip("no_hmtx")
        subtables = [table for table in _unicode_subtables(font) if table.format in WRITABLE_CMAP_FORMATS]
        if not subtables:
            raise _Skip("unsupported_cmap")
        kind = _outline_kind(font)
        if kind == "none":
            raise _Skip("unsupported_outline")
        if kind == "cid":
            top = font["CFF "].cff.topDictIndex[0]
            if not hasattr(top, "FDArray") or not hasattr(top, "FDSelect") or len(top.FDArray) == 0:
                raise _Skip("cid_without_fdarray")
        can_append = kind in ("glyf", "cff", "cid") and "fvar" not in font
        glyph_set = font.getGlyphSet()
        metrics = font["hmtx"].metrics
        quarter = _quarter_em(font)
        fixed = _fixed_pitch_width(font)
    except _Skip as skip:
        report.update(status="skipped", reason=skip.reason)
        return report

    blank_cache: dict[str, bool] = {}

    def blank(name: str) -> bool:
        if name not in blank_cache:
            blank_cache[name] = name in metrics and _is_blank(glyph_set, name)
        return blank_cache[name]

    def reuse_for(codepoint: int, mapping: dict[int, str]) -> str | None:
        if codepoint == SPACE:
            candidate = mapping.get(NBSP)
            return candidate if candidate and blank(candidate) else None
        preferred = [mapping[cp] for cp in (SPACE, NBSP) if cp in mapping]
        others = sorted({name for cp, name in mapping.items() if 0x2000 <= cp <= 0x200A or cp == 0x3000})
        for name in preferred + others:
            if name in metrics and abs(metrics[name][0] - quarter) <= 1 and blank(name):
                return name
        return None

    mapping = dict(best)
    filled: list[int] = []
    for codepoint in missing:
        label = f"U+{codepoint:04X}"
        name = reuse_for(codepoint, mapping)
        if name is not None:
            _map(font, codepoint, name, subtables)
            report["reused"][label] = name
        elif not can_append:
            report["unresolved"][label] = "variable_or_cff2_requires_existing_blank" if kind in ("glyf", "cff", "cid", "cff2") else kind
            continue
        else:
            width = fixed if fixed else quarter
            try:
                name = _append_glyph(font, kind, codepoint, width)
            except _Skip as skip:
                report["unresolved"][label] = skip.reason
                continue
            metrics = font["hmtx"].metrics
            blank_cache[name] = True
            _map(font, codepoint, name, subtables)
            report["added"][label] = {"glyph": name, "advance": width}
        mapping[codepoint] = name
        filled.append(codepoint)

    if filled:
        _update_os2(font, filled)
        for tag in ("hdmx", "LTSH", "VDMX"):
            if report["added"] and tag in font:
                del font[tag]
    if report["unresolved"]:
        report["status"] = "partial" if filled else "skipped"
        if not filled:
            report["reason"] = "unresolved"
    elif filled:
        report["status"] = "patched"
    return report


def process_path(source: Path, output: Path) -> dict[str, Any]:
    """Patch every face in ``source`` and write ``output``.

    When no face needs a change the file is copied byte for byte.
    """
    data = source.read_bytes()
    reports: list[dict[str, Any]] = []
    if data[:4] == b"ttcf":
        collection = TTCollection(str(source), lazy=False)
        try:
            for face in collection.fonts:
                reports.append(ensure_space_glyphs(face))
            changed = any(r["status"] in ("patched", "partial") for r in reports)
            if changed:
                output.parent.mkdir(parents=True, exist_ok=True)
                collection.save(str(output))
        finally:
            collection.close()
    else:
        font = TTFont(str(source), lazy=False)
        try:
            reports.append(ensure_space_glyphs(font))
            changed = reports[0]["status"] in ("patched", "partial")
            if changed:
                output.parent.mkdir(parents=True, exist_ok=True)
                font.save(str(output))
        finally:
            font.close()
    if not changed and source.resolve() != output.resolve():
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, output)
    return {"schema": SCHEMA, "changed": changed, "faces": reports}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="补全缺失的 U+0020 / U+2005 空白字形")
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args(argv)
    result = process_path(args.source, args.output)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
