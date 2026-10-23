#!/usr/bin/env python3
"""Build the verdict test corpus with fontTools and write expect.tsv next to it.

Every font is a tiny box-glyph font; many code points share one glyph so CJK fonts stay small.
expect.tsv columns: file, ttc_index, name_hint ('-' = none), verdict, reason.
Real system fonts (DejaVu) are added when the host has them.

Usage: make_test_fonts.py OUT_DIR
"""
from __future__ import annotations

import pathlib
import shutil
import sys

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTCollection, TTFont, newTable
from fontTools.ttLib.tables.DefaultTable import DefaultTable

LATIN = list(range(0x20, 0x7F))
DIGITS = list(range(0x30, 0x3A))


def box():
    pen = TTGlyphPen(None)
    pen.moveTo((50, 0))
    pen.lineTo((50, 700))
    pen.lineTo((450, 700))
    pen.lineTo((450, 0))
    pen.closePath()
    return pen.glyph()


def empty():
    return TTGlyphPen(None).glyph()


def build(codes, family, *, fixed_pitch=False, panose_mono=False, glyphs_per_code=False):
    """codes: iterable of code points. glyphs_per_code=False maps all non-ASCII to shared glyphs."""
    codes = sorted(set(codes))
    order = [".notdef", "space", "box", "box2"]
    cmap = {}
    for c in codes:
        if c == 0x20:
            cmap[c] = "space"
        elif glyphs_per_code and c < 0x80:
            name = f"g{c:04X}"
            order.append(name)
            cmap[c] = name
        else:
            cmap[c] = "box" if c % 2 else "box2"
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap(cmap)
    glyphs = {g: (empty() if g in (".notdef", "space") else box()) for g in order}
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics({g: (500, 50) for g in order})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": family, "styleName": "Regular"})
    os2 = {}
    if panose_mono:
        from fontTools.ttLib.tables.O_S_2f_2 import Panose
        p = Panose()
        p.bFamilyType = 2
        p.bProportion = 9
        os2["panose"] = p
    fb.setupOS2(**os2)
    fb.setupPost(isFixedPitch=1 if fixed_pitch else 0)
    return fb.font


def save(font: TTFont, path: pathlib.Path, flavor=None):
    if flavor:
        font.flavor = flavor
    font.save(str(path))


def main() -> int:
    out = pathlib.Path(sys.argv[1]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    rows: list[tuple[str, int, str, str, str]] = []

    def add(name, font, verdict, reason, hint="-", ttc=0, flavor=None):
        save(font, out / name, flavor)
        rows.append((name, ttc, hint, verdict, reason))

    cjk_bmp = list(range(0x4E00, 0x4E00 + 3000))
    add("latin_body.ttf", build(LATIN, "Sample Sans", glyphs_per_code=True), "replace_latin", "body_latin")
    add("cjk_body.ttf", build(LATIN + cjk_bmp, "Sample Hei"), "replace_cjk", "body_cjk")
    # Supplementary code points force a (3,10) format 12 subtable.
    add("cjk_ext_f12.ttf", build(LATIN + cjk_bmp + list(range(0x20000, 0x20010)), "Sample Song"),
        "replace_cjk", "body_cjk")
    add("cjk_only_f12.ttf", build(list(range(0x3400, 0x3400 + 1200)) + list(range(0x20000, 0x20004)), "Sample Kai"),
        "replace_cjk", "body_cjk")
    add("pua_ligature.ttf", build(LATIN + list(range(0xE000, 0xE400)), "Alpha Lig"), "keep", "private_use")
    add("pua_only.ttf", build(list(range(0xE000, 0xE080)), "Alpha Pict"), "keep", "private_use")
    add("pua_plane15.ttf", build(LATIN + list(range(0xF0000, 0xF0100)), "Alpha Supp"), "keep", "private_use")
    # A text face with a few dozen PUA ligatures (DejaVu-like) stays a body font.
    add("pua_few_text.ttf", build(LATIN + list(range(0xE000, 0xE060)), "Sample Text"), "replace_latin", "body_latin")
    add("digits_only.ttf", build(DIGITS + [0x3A, 0x2E], "Alpha Seven"), "keep", "digits_only")
    add("display_caps.ttf", build(list(range(0x41, 0x5B)) + [0x20], "Alpha Caps"), "keep", "not_text")
    add("mono_post.ttf", build(LATIN, "Sample Code", fixed_pitch=True), "keep", "monospace")
    add("mono_panose.ttf", build(LATIN, "Sample Term", panose_mono=True), "keep", "monospace")
    add("named_icons.ttf", build(LATIN, "MyIcons"), "keep", "name_token")
    add("named_symbol.ttf", build(LATIN, "Sample Symbol Pro"), "keep", "name_token")
    rows.append(("latin_body.ttf", 0, "assets/fonts/fontawesome-webfont.ttf", "keep", "name_token"))
    rows.append(("latin_body.ttf", 0, "/data/app/com.icons.app/files/Roboto-Regular.ttf", "replace_latin",
                 "body_latin"))
    rows.append(("latin_body.ttf", 0, "res/font/inter_medium.ttf", "replace_latin", "body_latin"))

    color = build(LATIN, "Sample Color")
    colr = DefaultTable("COLR")
    colr.data = b"\x00" * 14
    color["COLR"] = colr
    add("color_colr.ttf", color, "keep", "color_table")

    sym = build(list(range(0xF020, 0xF0FF)), "Sample Wing")
    for st in sym["cmap"].tables:
        st.platformID, st.platEncID = 3, 0
    sym["cmap"].tables = [t for t in sym["cmap"].tables if t.format == 4][:1]
    add("symbol_cmap.ttf", sym, "keep", "symbol_cmap")

    nocmap = build(LATIN, "Sample Empty")
    del nocmap["cmap"]
    add("no_cmap.ttf", nocmap, "keep", "no_cmap")

    add("latin_body.woff", build(LATIN, "Sample Sans"), "keep", "woff", flavor="woff")

    latin_bytes = (out / "latin_body.ttf").read_bytes()
    (out / "truncated.ttf").write_bytes(latin_bytes[:100])
    rows.append(("truncated.ttf", 0, "-", "keep", "parse_error"))
    (out / "tiny.bin").write_bytes(b"\x00\x01\x00")
    rows.append(("tiny.bin", 0, "-", "keep", "too_small"))
    (out / "garbage.bin").write_bytes(bytes((i * 37 + 11) & 0xFF for i in range(4096)))
    rows.append(("garbage.bin", 0, "-", "keep", "parse_error"))

    coll = TTCollection()
    coll.fonts = [TTFont(str(out / "latin_body.ttf")), TTFont(str(out / "cjk_body.ttf"))]
    coll.save(str(out / "pair.ttc"))
    rows.append(("pair.ttc", 0, "-", "replace_latin", "body_latin"))
    rows.append(("pair.ttc", 1, "-", "replace_cjk", "body_cjk"))
    rows.append(("pair.ttc", 2, "-", "keep", "parse_error"))
    rows.append(("latin_body.ttf", 1, "-", "keep", "parse_error"))

    for src, verdict, reason in (
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "replace_latin", "body_latin"),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", "keep", "monospace"),
    ):
        p = pathlib.Path(src)
        if p.is_file():
            shutil.copyfile(p, out / p.name)
            rows.append((p.name, 0, "-", verdict, reason))

    with open(out / "expect.tsv", "w", encoding="utf-8") as f:
        for r in rows:
            f.write("\t".join(str(x) for x in r) + "\n")
    print(f"corpus: {len(rows)} cases in {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
