#!/usr/bin/env python3
"""Tests for common/font_space_compat.py (U+0020 / U+2005 blank glyph fill)."""
from __future__ import annotations

import argparse
import io
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EMBEDDED_FONTTOOLS = ROOT / "common/python/lib/python3.14/site-packages"
if EMBEDDED_FONTTOOLS.is_dir():
    sys.path.insert(0, str(EMBEDDED_FONTTOOLS))
sys.path.insert(0, str(ROOT / "common"))

from fontTools.cffLib import FDArrayIndex, FDSelect, FontDict  # noqa: E402
from fontTools.fontBuilder import FontBuilder  # noqa: E402
from fontTools.pens.boundsPen import BoundsPen  # noqa: E402
from fontTools.pens.t2CharStringPen import T2CharStringPen  # noqa: E402
from fontTools.pens.ttGlyphPen import TTGlyphPen  # noqa: E402
from fontTools.ttLib import TTCollection, TTFont  # noqa: E402

from font_space_compat import ensure_space_glyphs, process_path  # noqa: E402

FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        FAILURES.append(message)
        print(f"FAIL: {message}", file=sys.stderr)


def box_tt():
    pen = TTGlyphPen(None)
    pen.moveTo((50, 0)); pen.lineTo((450, 0)); pen.lineTo((450, 700)); pen.lineTo((50, 700)); pen.closePath()
    return pen.glyph()


def box_cff(width: int):
    pen = T2CharStringPen(width, None)
    pen.moveTo((50, 0)); pen.lineTo((450, 0)); pen.lineTo((450, 700)); pen.lineTo((50, 700)); pen.closePath()
    return pen.getCharString()


def empty_tt():
    return TTGlyphPen(None).glyph()


def empty_cff(width: int):
    return T2CharStringPen(width, None).getCharString()


def make_font(*, cff: bool = False, blanks: dict[int, int] | None = None, upem: int = 1000,
              mono: bool = False, variable: bool = False, vertical: bool = False) -> TTFont:
    """Font with A, 中 and optional blank glyphs {codepoint: advance}."""
    blanks = blanks or {}
    names = {ord("A"): "A", ord("中"): "uni4E2D"}
    advances = {".notdef": 500, "A": 500, "uni4E2D": upem}
    if mono:
        advances = {".notdef": 600, "A": 600, "uni4E2D": 600}
    for codepoint, advance in blanks.items():
        name = "space" if codepoint == 0x20 else f"uni{codepoint:04X}"
        names[codepoint] = name
        advances[name] = advance
    order = [".notdef", "A", "uni4E2D", *[n for n in names.values() if n not in ("A", "uni4E2D")]]
    builder = FontBuilder(upem, isTTF=not cff)
    builder.setupGlyphOrder(order)
    builder.setupCharacterMap(names)
    if cff:
        charstrings = {n: (empty_cff(advances[n]) if n in names.values() and n not in ("A", "uni4E2D") else box_cff(advances[n])) for n in order}
        builder.setupCFF("SpaceTest", {"FullName": "Space Test"}, charstrings, {})
        metrics = {n: (advances[n], 0 if n in names.values() and n not in ("A", "uni4E2D") else 50) for n in order}
    else:
        glyphs = {n: (empty_tt() if n in names.values() and n not in ("A", "uni4E2D") else box_tt()) for n in order}
        builder.setupGlyf(glyphs)
        metrics = {n: (advances[n], 50 if glyphs[n].numberOfContours else 0) for n in order}
    builder.setupHorizontalMetrics(metrics)
    builder.setupHorizontalHeader(ascent=880, descent=-120)
    builder.setupNameTable({"familyName": "Space Test", "styleName": "Regular"})
    builder.setupOS2(sTypoAscender=880, sTypoDescender=-120, usWinAscent=880, usWinDescent=120)
    builder.setupPost(isFixedPitch=1 if mono else 0)
    if vertical:
        builder.setupVerticalHeader(ascent=500, descent=-500)
        builder.setupVerticalMetrics({n: (upem, 120) for n in order})
    if variable:
        builder.setupFvar([("wght", 100, 400, 900, "Weight")], [])
    return reload(builder.font)


def reload(font: TTFont) -> TTFont:
    buffer = io.BytesIO()
    font.save(buffer)
    buffer.seek(0)
    return TTFont(buffer)


def to_bytes(font: TTFont) -> bytes:
    buffer = io.BytesIO()
    font.save(buffer)
    return buffer.getvalue()


def make_cid(font: TTFont) -> TTFont:
    """Convert a name-keyed CFF test font into a CID-keyed one."""
    for table in font["cmap"].tables:
        _ = table.cmap
    _ = font["hmtx"].metrics
    cff = font["CFF "].cff
    top = cff.topDictIndex[0]
    old_order = font.getGlyphOrder()
    new_order = [".notdef" if i == 0 else f"cid{i:05d}" for i in range(len(old_order))]
    rename = dict(zip(old_order, new_order))
    charstrings = top.CharStrings
    if charstrings.charStringsAreIndexed:
        charstrings.charStrings = {rename[name]: index for name, index in charstrings.charStrings.items()}
    else:
        charstrings.charStrings = {rename[name]: cs for name, cs in charstrings.charStrings.items()}
    fd = FontDict()
    fd.setCFF2(False)
    fd.Private = top.Private
    fd.FontName = "SpaceTest-FD0"
    fdarray = FDArrayIndex()
    fdarray.append(fd)
    top.FDArray = fdarray
    top.FDArray.strings = cff.strings
    top.FDArray.GlobalSubrs = cff.GlobalSubrs
    fdselect = FDSelect()
    fdselect.format = 3
    fdselect.gidArray = [0] * len(new_order)
    top.FDSelect = fdselect
    top.ROS = ("Adobe", "Identity", 0)
    top.CIDCount = len(new_order)
    del top.rawDict["Private"]
    del top.Private
    top.charset = new_order
    font.setGlyphOrder(new_order)
    cmap = font["cmap"]
    for table in cmap.tables:
        table.cmap = {cp: rename[name] for cp, name in table.cmap.items()}
    hmtx = font["hmtx"]
    hmtx.metrics = {rename[name]: value for name, value in hmtx.metrics.items()}
    return reload(font)


def advance_of(font: TTFont, codepoint: int) -> int:
    name = font.getBestCmap()[codepoint]
    return font["hmtx"].metrics[name][0]


def is_blank(font: TTFont, codepoint: int) -> bool:
    glyph_set = font.getGlyphSet()
    pen = BoundsPen(glyph_set)
    glyph_set[font.getBestCmap()[codepoint]].draw(pen)
    return pen.bounds is None


def charstring_width(font: TTFont, codepoint: int) -> int:
    glyph_set = font.getGlyphSet()
    return glyph_set[font.getBestCmap()[codepoint]].width


def test_tt_missing_both() -> None:
    font = make_font()
    order_before = font.getGlyphOrder()[:]
    report = ensure_space_glyphs(font)
    check(report["status"] == "patched", f"tt both: status {report}")
    check(report["added"].get("U+0020", {}).get("advance") == 250, f"tt both: space width {report}")
    check(report["reused"].get("U+2005") == "space", f"tt both: 2005 should reuse the quarter-em space {report}")
    font = reload(font)
    check(font.getGlyphOrder()[: len(order_before)] == order_before, "tt both: existing glyph ids moved")
    check(font["maxp"].numGlyphs == len(order_before) + 1, "tt both: numGlyphs")
    for cp in (0x20, 0x2005):
        check(cp in font.getBestCmap(), f"tt both: U+{cp:04X} not mapped")
        check(advance_of(font, cp) == 250 and is_blank(font, cp), f"tt both: U+{cp:04X} not a 250 blank")
    for table in font["cmap"].tables:
        if table.isUnicode():
            check(0x20 in table.cmap and 0x2005 in table.cmap, f"tt both: subtable {table.platformID}/{table.platEncID} incomplete")
    check(font["OS/2"].usFirstCharIndex == 0x20, "tt both: usFirstCharIndex")


def test_tt_space_wide() -> None:
    font = make_font(blanks={0x20: 300}, upem=2048)
    report = ensure_space_glyphs(font)
    check(report["status"] == "patched" and "U+2005" in report["added"], f"tt wide: {report}")
    font = reload(font)
    check(advance_of(font, 0x20) == 300, "tt wide: space advance changed")
    check(advance_of(font, 0x2005) == 512 and is_blank(font, 0x2005), "tt wide: 2005 should be upem/4 blank")
    check(font.getBestCmap()[0x2005] != font.getBestCmap()[0x20], "tt wide: 2005 must not reuse a 300 space")


def test_tt_reuse_nbsp() -> None:
    font = make_font(blanks={0xA0: 260, 0x2005: 250})
    count = len(font.getGlyphOrder())
    report = ensure_space_glyphs(font)
    check(report["reused"].get("U+0020") == "uni00A0" and not report["added"], f"tt nbsp: {report}")
    font = reload(font)
    check(len(font.getGlyphOrder()) == count and advance_of(font, 0x20) == 260, "tt nbsp: should map to nbsp only")


def test_unchanged_bytes() -> None:
    for cff in (False, True):
        font = make_font(cff=cff, blanks={0x20: 230, 0x2005: 250})
        before = to_bytes(font)
        report = ensure_space_glyphs(font)
        check(report["status"] == "unchanged", f"unchanged cff={cff}: {report}")
        check(to_bytes(font) == before, f"unchanged cff={cff}: bytes differ after no-op")


def test_cff() -> None:
    font = make_font(cff=True, vertical=True)
    report = ensure_space_glyphs(font)
    check(report["status"] == "patched", f"cff: {report}")
    font = reload(font)
    for cp in (0x20, 0x2005):
        check(is_blank(font, cp) and charstring_width(font, cp) == 250 and advance_of(font, cp) == 250, f"cff: U+{cp:04X} blank 250")
    name = font.getBestCmap()[0x20]
    check(name in font["vmtx"].metrics, "cff: vmtx missing new glyph")
    check(font["CFF "].cff.topDictIndex[0].charset == font.getGlyphOrder(), "cff: charset mismatch")


def test_cid() -> None:
    font = make_cid(make_font(cff=True, upem=1000))
    check(hasattr(font["CFF "].cff.topDictIndex[0], "ROS"), "cid fixture is not CID-keyed")
    count = len(font.getGlyphOrder())
    report = ensure_space_glyphs(font)
    check(report["status"] == "patched", f"cid: {report}")
    added = report["added"].get("U+0020", {}).get("glyph", "")
    check(added == f"cid{count:05d}", f"cid: unexpected glyph name {added}")
    font = reload(font)
    top = font["CFF "].cff.topDictIndex[0]
    check(len(top.FDSelect) == count + 1, "cid: FDSelect not extended")
    check(is_blank(font, 0x20) and charstring_width(font, 0x20) == 250, "cid: blank 250")
    check(font.getBestCmap()[0x2005] == font.getBestCmap()[0x20], "cid: 2005 reuse")


def test_cid_without_fdarray() -> None:
    font = make_cid(make_font(cff=True))
    top = font["CFF "].cff.topDictIndex[0]
    top.rawDict.pop("FDArray", None)
    top.__dict__.pop("FDArray", None)
    report = ensure_space_glyphs(font)
    check(report["status"] == "skipped" and report.get("reason") == "cid_without_fdarray", f"cid nofd: {report}")
    check(0x20 not in font.getBestCmap(), "cid nofd: cmap modified")


def test_variable_reuse_only() -> None:
    font = make_font(variable=True)
    before = to_bytes(font)
    report = ensure_space_glyphs(font)
    check(report["status"] == "skipped" and len(report["unresolved"]) == 2, f"var none: {report}")
    check(to_bytes(font) == before, "var none: bytes changed")
    font = make_font(variable=True, blanks={0xA0: 250})
    report = ensure_space_glyphs(font)
    check(report["status"] == "patched" and not report["added"], f"var nbsp: {report}")
    check(reload(font).getBestCmap()[0x2005] == "uni00A0", "var nbsp: 2005 should reuse quarter-em nbsp")


def test_fixed_pitch() -> None:
    font = make_font(mono=True)
    report = ensure_space_glyphs(font)
    check(report["added"].get("U+0020", {}).get("advance") == 600, f"mono: {report}")
    font = reload(font)
    check(advance_of(font, 0x20) == 600, "mono: space should keep fixed pitch")


def test_no_unicode_cmap() -> None:
    font = make_font()
    font["cmap"].tables = [t for t in font["cmap"].tables if not t.isUnicode()]
    report = ensure_space_glyphs(font)
    check(report["status"] == "skipped" and report.get("reason") == "no_unicode_cmap", f"nocmap: {report}")


def test_cli_and_collection(tmp: Path) -> None:
    ready = tmp / "ready.ttf"
    make_font(blanks={0x20: 230, 0x2005: 250}).save(str(ready))
    out = tmp / "ready-out.ttf"
    result = process_path(ready, out)
    check(not result["changed"] and out.read_bytes() == ready.read_bytes(), "cli: unchanged file not byte identical")

    collection = TTCollection()
    collection.fonts = [make_font(blanks={0x20: 230, 0x2005: 250}), make_font()]
    ttc = tmp / "pair.ttc"
    collection.save(str(ttc))
    out = tmp / "pair-out.ttc"
    result = process_path(ttc, out)
    check(result["changed"] and [f["status"] for f in result["faces"]] == ["unchanged", "patched"], f"ttc: {result}")
    reloaded = TTCollection(str(out))
    check(all(0x2005 in face.getBestCmap() for face in reloaded.fonts), "ttc: faces incomplete")


def test_real_font(path: Path, tmp: Path) -> None:
    font = TTFont(str(path))
    had = {cp: cp in font.getBestCmap() for cp in (0x20, 0x2005)}
    before = to_bytes(font)
    report = ensure_space_glyphs(font)
    if all(had.values()):
        check(report["status"] == "unchanged" and to_bytes(font) == before, f"real: should be unchanged {report}")
        out = tmp / "real.ttf"
        process_path(path, out)
        check(out.read_bytes() == path.read_bytes(), "real: cli copy not identical")
    else:
        check(report["status"] == "patched", f"real: {report}")
        check(all(cp in reload(font).getBestCmap() for cp in (0x20, 0x2005)), "real: not filled")
    # Remove U+2005 from a copy and make sure it is filled back as a blank.
    font = TTFont(str(path))
    for table in font["cmap"].tables:
        if table.isUnicode():
            table.cmap.pop(0x2005, None)
    report = ensure_space_glyphs(font)
    font = reload(font)
    check(report["status"] == "patched" and is_blank(font, 0x2005), f"real stripped: {report}")
    check(abs(advance_of(font, 0x2005) - font["head"].unitsPerEm / 4) <= 1, "real stripped: width")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--font", type=Path, help="real TrueType font for a smoke run")
    args = parser.parse_args()
    test_tt_missing_both()
    test_tt_space_wide()
    test_tt_reuse_nbsp()
    test_unchanged_bytes()
    test_cff()
    test_cid()
    test_cid_without_fdarray()
    test_variable_reuse_only()
    test_fixed_pitch()
    test_no_unicode_cmap()
    with tempfile.TemporaryDirectory() as tmp_name:
        tmp = Path(tmp_name)
        test_cli_and_collection(tmp)
        if args.font and args.font.is_file():
            test_real_font(args.font, tmp)
    if FAILURES:
        print(json.dumps({"failures": FAILURES}, ensure_ascii=False), file=sys.stderr)
        return 1
    print("font_space_compat_test: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
