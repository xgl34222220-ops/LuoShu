#!/usr/bin/env python3
"""Tiny generated fonts for font capability tests (no system fonts needed).

Each glyph is a rectangle whose stem width encodes the weight, so a test can
prove which master/instance ended up in a slot by measuring one outline.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTCollection, TTFont

LATIN = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
HANT = "這個們說時國會來後對當過還實讓體點樣與麼開關問題門東車長書見"
HAN = "的一是不了人我在有他这中大来上个国到说们为子和你地出道也时年得就那要下以生会自着去之过家学对可中文字体系统默认洛书汉字"


def _rect(width: int):
    pen = TTGlyphPen(None)
    pen.moveTo((50, 0)); pen.lineTo((50, 700)); pen.lineTo((50 + width, 700)); pen.lineTo((50 + width, 0))
    pen.closePath()
    return pen.glyph()


def build(path: Path, *, family: str = "Demo", style: str = "Regular", weight: int = 400,
          italic: bool = False, text: str = LATIN, stem: int | None = None,
          color: bool = False) -> Path:
    chars = sorted(set(text))
    names = [".notdef"] + [f"g{ord(ch):04X}" for ch in chars]
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder(names)
    fb.setupCharacterMap({ord(ch): f"g{ord(ch):04X}" for ch in chars})
    width = stem if stem is not None else max(10, weight // 4)
    glyphs = {name: _rect(width) for name in names}
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics({name: (600, 50) for name in names})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": family, "styleName": style})
    fs_selection = 0x01 if italic else (0x40 if style == "Regular" else 0)
    fb.setupOS2(usWeightClass=weight, fsSelection=fs_selection, sTypoAscender=800,
                sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
    fb.setupPost(italicAngle=-12 if italic else 0)
    fb.font["head"].macStyle = (0x02 if italic else 0) | (0x01 if weight >= 700 else 0)
    if color:
        from fontTools.colorLib.builder import buildCOLR, buildCPAL
        first = names[1]
        fb.font["COLR"] = buildCOLR({first: [(first, 0)]})
        fb.font["CPAL"] = buildCPAL([[(1.0, 0.0, 0.0, 1.0)]])
    # Real fonts are never a few hundred bytes; LuoShu's import and anchor
    # guards reject tiny outputs, so pad with an inert private table.
    from fontTools.ttLib.tables.DefaultTable import DefaultTable
    pad = DefaultTable("zPad")
    pad.data = b"\0" * 6000
    fb.font["zPad"] = pad
    path.parent.mkdir(parents=True, exist_ok=True)
    fb.save(str(path))
    return path


def build_variable(path: Path, *, family: str = "DemoVF", low: int = 100, high: int = 900,
                   default: int = 400, text: str = LATIN) -> Path:
    """Two-master wght VF built with varLib (rect stem grows with weight)."""
    from fontTools.designspaceLib import AxisDescriptor, DesignSpaceDocument, SourceDescriptor
    from fontTools import varLib
    work = path.parent / (path.stem + "-masters")
    work.mkdir(parents=True, exist_ok=True)
    masters = []
    for value in sorted({low, default, high}):
        master = work / f"m{value}.ttf"
        build(master, family=family, style="Regular", weight=value, text=text, stem=max(10, value // 4))
        masters.append((value, master))
    doc = DesignSpaceDocument()
    axis = AxisDescriptor()
    axis.tag, axis.name, axis.minimum, axis.default, axis.maximum = "wght", "Weight", low, default, high
    doc.addAxis(axis)
    for value, master in masters:
        source = SourceDescriptor()
        source.path = str(master)
        source.location = {"Weight": value}
        doc.addSource(source)
    font, _, _ = varLib.build(doc)
    font["OS/2"].usWeightClass = default
    path.parent.mkdir(parents=True, exist_ok=True)
    font.save(str(path))
    return path


def build_collection(path: Path, members: list[Path]) -> Path:
    fonts = [TTFont(str(member), lazy=False) for member in members]
    try:
        collection = TTCollection()
        collection.fonts = fonts
        collection.save(str(path))
    finally:
        for font in fonts:
            font.close()
    return path


def stem_width(path: Path, char: str = "A", index: int = -1) -> int:
    kwargs = {"fontNumber": index} if index >= 0 else {}
    with TTFont(str(path), **kwargs) as font:
        glyph = font["glyf"][font.getBestCmap()[ord(char)]]
        glyph.recalcBounds(font["glyf"])
        return int(glyph.xMax - glyph.xMin)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=("static", "variable", "collection"))
    parser.add_argument("output")
    parser.add_argument("--family", default="Demo")
    parser.add_argument("--style", default="Regular")
    parser.add_argument("--weight", type=int, default=400)
    parser.add_argument("--italic", action="store_true")
    parser.add_argument("--color", action="store_true")
    parser.add_argument("--han", action="store_true")
    parser.add_argument("--hant", action="store_true")
    parser.add_argument("--members", nargs="*", default=[])
    args = parser.parse_args()
    text = LATIN + (HAN if args.han else "") + (HANT if args.hant else "")
    if args.kind == "static":
        build(Path(args.output), family=args.family, style=args.style, weight=args.weight,
              italic=args.italic, text=text, color=args.color)
    elif args.kind == "variable":
        build_variable(Path(args.output), family=args.family, text=text)
    else:
        build_collection(Path(args.output), [Path(item) for item in args.members])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
