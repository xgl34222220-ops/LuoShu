#!/usr/bin/env python3
"""Add real blank glyphs for missing Unicode spaces before font deployment.

Ported from 字域 Ziyu v1.4.8 ``common/font_space_compat.py``
(https://github.com/shishui611-art/Ziyu, author 酷安@柔性体, GPL-3.0-only;
first added in Ziyu commit 025e64286b3daf286bdb887d514c570ea9353e03, last
changed in d9b9b61898b0ff00f0db5d7d149ab2ec81b8a8fd). See
THIRD_PARTY_NOTICES.md for the attribution and the LuoShu changes.

Contract used by the LuoShu builders:

* A font whose U+0020 and U+2005 already map to real glyphs is not touched.
* Missing spaces get a dedicated empty glyph appended to the end of the glyph
  order (advance = unitsPerEm / 4). Existing glyphs, their IDs, outlines,
  advances, names and the weight metadata are never changed.
* Variable fonts (and fonts at the glyph limit) only reuse an existing space
  glyph through cmap, so glyph-indexed variation data stays valid.
* Fonts that cannot be repaired safely are reported as ``skipped`` before any
  table is modified, so the caller keeps its previous behaviour.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    from fontTools.ttLib import TTFont

SCHEMA = "font-space-compat-v1"
SPACE_CODEPOINTS = (0x0020, 0x2005)


class _NoGlyphName(ValueError):
    pass


def _cff_top(font: "TTFont"):
    if "CFF " in font:
        return font["CFF "].cff.topDictIndex[0]
    if "CFF2" in font:
        return font["CFF2"].cff.topDictIndex[0]
    return None


def _new_glyph_name(font: "TTFont", codepoint: int, occupied: set[str]) -> str:
    top = _cff_top(font)
    if top is not None and hasattr(top, "ROS"):
        used_cids = []
        for name in occupied:
            if name.startswith("cid"):
                try:
                    used_cids.append(int(name[3:]))
                except ValueError:
                    pass
        cid = max(used_cids, default=-1) + 1
        if cid > 0xFFFF:
            raise _NoGlyphName("CFF 字体没有可用的 CID 编号来补空白字形")
        name = f"cid{cid:05d}"
    else:
        name = f"luoshuSpace{codepoint:04X}"
        suffix = 1
        while name in occupied:
            name = f"luoshuSpace{codepoint:04X}_{suffix}"
            suffix += 1
    if name in occupied:
        raise _NoGlyphName(f"空白字形名称冲突：{name}")
    return name


def _append_cff_glyph(font: "TTFont", glyph_name: str, advance: int, tag: str) -> None:
    from fontTools.pens.t2CharStringPen import T2CharStringPen

    cff = font[tag].cff
    top = cff.topDictIndex[0]
    char_strings = top.CharStrings
    old_order = list(font.getGlyphOrder())

    # Convert FontTools' binary glyph-ID view before adding a name-keyed glyph.
    if char_strings.charStringsAreIndexed:
        char_strings.charStrings = {name: char_strings[name] for name in old_order}
        char_strings.charStringsAreIndexed = 0

    is_cff2 = tag == "CFF2"
    if hasattr(top, "FDArray"):
        selector = 0
        private = getattr(top.FDArray[selector], "Private", None)
    else:
        selector = None
        private = top.Private

    pen = T2CharStringPen(None if is_cff2 else advance, None, CFF2=is_cff2)
    pen.moveTo((0, 0))
    pen.endPath()
    glyph = pen.getCharString(private=private, globalSubrs=cff.GlobalSubrs)
    if selector is not None:
        glyph.fdSelectIndex = selector
    char_strings.charStrings[glyph_name] = glyph

    new_order = old_order + [glyph_name]
    if hasattr(top, "charset"):
        top.charset = new_order
    if hasattr(top, "FDSelect") and len(top.FDSelect) > 0:
        top.FDSelect.append(selector or 0)
    font.setGlyphOrder(new_order)


def _append_blank_glyph(font: "TTFont", glyph_name: str, advance: int) -> None:
    if "glyf" in font:
        from fontTools.pens.ttGlyphPen import TTGlyphPen

        old_order = list(font.getGlyphOrder())
        font.setGlyphOrder(old_order + [glyph_name])
        glyph = TTGlyphPen(None).glyph()
        glyph.numberOfContours = 0
        glyph.xMin = glyph.yMin = glyph.xMax = glyph.yMax = 0
        font["glyf"][glyph_name] = glyph
        if "gvar" in font:
            font["gvar"].variations[glyph_name] = []
    else:
        _append_cff_glyph(font, glyph_name, advance, "CFF " if "CFF " in font else "CFF2")

    font["hmtx"].metrics[glyph_name] = (advance, 0)
    if "vmtx" in font:
        font["vmtx"].metrics[glyph_name] = (int(font["head"].unitsPerEm), 0)
    if "maxp" in font:
        font["maxp"].numGlyphs = len(font.getGlyphOrder())
    if "post" in font and float(font["post"].formatType) == 1.0:
        # Format 1 only knows the standard 258 glyph names.
        font["post"].formatType = 2.0
    for tag in ("DSIG", "LTSH", "hdmx", "VDMX"):
        if tag in font:
            del font[tag]


def _existing_space_glyph(font: "TTFont", codepoint: int) -> tuple[int, str] | None:
    """Reuse another supported space mapping when glyphs must not be appended."""
    cmap = font.getBestCmap() or {}
    glyph_names = set(font.getGlyphOrder())
    for source_codepoint in SPACE_CODEPOINTS:
        if source_codepoint == codepoint:
            continue
        glyph_name = cmap.get(source_codepoint)
        if glyph_name and glyph_name != ".notdef" and glyph_name in glyph_names:
            return source_codepoint, glyph_name
    return None


def _missing_spaces(font: "TTFont") -> list[int]:
    cmap = (font.getBestCmap() or {}) if "cmap" in font else {}
    glyph_names = set(font.getGlyphOrder())
    return [
        codepoint
        for codepoint in SPACE_CODEPOINTS
        if cmap.get(codepoint) not in glyph_names or cmap.get(codepoint) == ".notdef"
    ]


def _skip(reason: str, missing: list[int]) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "status": "skipped",
        "reason": reason,
        "missing": [f"U+{codepoint:04X}" for codepoint in missing],
        "added": [],
        "reused": [],
        "unresolved": [],
    }


def _preflight(font: "TTFont") -> str | None:
    """Return why the font cannot be repaired, checked before any mutation."""
    if "cmap" not in font:
        return "字体缺少 Unicode cmap，无法映射空格字形"
    if not any(
        table.format != 14 and table.isUnicode() and hasattr(table, "cmap")
        for table in font["cmap"].tables
    ):
        return "字体没有可写入的 Unicode cmap 子表"
    if "head" not in font or int(font["head"].unitsPerEm) <= 0:
        return "字体 unitsPerEm 无效"
    if "hmtx" not in font:
        return "字体缺少 hmtx 表，无法设置空格宽度"
    if "glyf" not in font and "CFF " not in font and "CFF2" not in font:
        return "字体轮廓格式不支持自动补空格字形"
    top = _cff_top(font) if "glyf" not in font else None
    if top is not None and hasattr(top, "FDArray") and not top.FDArray:
        return "CID 字体缺少 FDArray，无法安全添加空白字形"
    return None


def ensure_space_glyphs(font: "TTFont") -> dict[str, Any]:
    """Map absent U+0020/U+2005 to dedicated blank glyphs with correct advances.

    Returns a JSON-serialisable report. ``status`` is ``unchanged`` when no
    space was missing (the font object is not modified at all), ``repaired``
    when every missing space was fixed, ``partial`` when only some could be
    fixed and ``skipped`` when the font cannot be repaired safely.
    """
    missing = _missing_spaces(font)
    if not missing:
        return {"schema": SCHEMA, "status": "unchanged", "added": [], "reused": [], "unresolved": []}

    reason = _preflight(font)
    if reason is not None:
        return _skip(reason, missing)

    unicode_tables = [
        table for table in font["cmap"].tables
        if table.format != 14 and table.isUnicode() and hasattr(table, "cmap")
    ]
    upem = int(font["head"].unitsPerEm)
    occupied = set(font.getGlyphOrder())
    added: list[dict[str, Any]] = []
    reused: list[dict[str, Any]] = []
    unresolved: list[dict[str, str]] = []
    for codepoint in missing:
        # Variable fonts have glyph-indexed variation data. Reuse an existing
        # space mapping instead of changing the glyph order or gvar table.
        if "fvar" in font or len(font.getGlyphOrder()) >= 0xFFFF:
            fallback = _existing_space_glyph(font, codepoint)
            if fallback is None:
                unresolved.append({
                    "codepoint": f"U+{codepoint:04X}",
                    "reason": (
                        "variable font has no reusable space glyph"
                        if "fvar" in font else "OpenType glyph limit"
                    ),
                })
                continue
            source_codepoint, glyph_name = fallback
            for table in unicode_tables:
                table.cmap[codepoint] = glyph_name
            reused.append({
                "codepoint": f"U+{codepoint:04X}",
                "glyph": glyph_name,
                "source": f"U+{source_codepoint:04X}",
            })
            continue
        try:
            glyph_name = _new_glyph_name(font, codepoint, occupied)
        except _NoGlyphName as error:
            unresolved.append({"codepoint": f"U+{codepoint:04X}", "reason": str(error)})
            continue
        advance = max(1, int(round(upem / 4)))
        _append_blank_glyph(font, glyph_name, advance)
        occupied.add(glyph_name)
        for table in unicode_tables:
            table.cmap[codepoint] = glyph_name
        added.append({"codepoint": f"U+{codepoint:04X}", "glyph": glyph_name, "advance": advance})

    repaired = font.getBestCmap() or {}
    for item in [*added, *reused]:
        codepoint = int(item["codepoint"][2:], 16)
        if repaired.get(codepoint) != item["glyph"]:
            raise ValueError(f"空格字形 U+{codepoint:04X} 映射校验失败")
    status = "repaired" if added or reused else "unchanged"
    if unresolved:
        status = "partial" if added or reused else "skipped"
    return {
        "schema": SCHEMA,
        "status": status,
        "added": added,
        "reused": reused,
        "unresolved": unresolved,
        "unitsPerEm": upem,
    }


def _save_repaired(font: "TTFont", output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    os.close(descriptor)
    try:
        font.save(temporary, reorderTables=False)
        if os.path.getsize(temporary) < 1024:
            raise ValueError("补空格后的字体输出异常小")
        os.chmod(temporary, 0o644)
        os.replace(temporary, output)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _copy_unchanged(source: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    os.close(descriptor)
    try:
        os.unlink(temporary)
        shutil.copyfile(source, temporary)
        os.chmod(temporary, 0o644)
        os.replace(temporary, output)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        if not args.input.is_file() or args.input.stat().st_size < 12:
            raise ValueError(f"字体源文件不可用：{args.input}")
        if args.input.resolve() == args.output.resolve():
            raise ValueError("输入和输出必须是不同文件")
        from fontTools.ttLib import TTFont

        font = TTFont(str(args.input), lazy=False, recalcTimestamp=False)
        try:
            report = ensure_space_glyphs(font)
            if report.get("added") or report.get("reused"):
                _save_repaired(font, args.output)
            else:
                _copy_unchanged(args.input, args.output)
        finally:
            font.close()
        print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
        return 0
    except Exception as error:
        args.output.unlink(missing_ok=True)
        print(f"font space compatibility failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
