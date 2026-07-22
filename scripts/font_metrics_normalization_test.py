#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
EMBEDDED_FONTTOOLS = ROOT / "common/python/lib/python3.14/site-packages"
if EMBEDDED_FONTTOOLS.is_dir():
    sys.path.insert(0, str(EMBEDDED_FONTTOOLS))
sys.path.insert(0, str(ROOT / "common"))

from fontTools.fontBuilder import FontBuilder  # noqa: E402
from fontTools.pens.boundsPen import BoundsPen  # noqa: E402
from fontTools.pens.ttGlyphPen import TTGlyphPen  # noqa: E402
from fontTools.ttLib import TTFont  # noqa: E402

from composite_font import build  # noqa: E402
from font_metrics_normalize import normalize_path  # noqa: E402


def rectangle(x0: int, y0: int, x1: int, y1: int):
    pen = TTGlyphPen(None)
    pen.moveTo((x0, y0)); pen.lineTo((x1, y0)); pen.lineTo((x1, y1)); pen.lineTo((x0, y1)); pen.closePath()
    return pen.glyph()


def make_font(path: Path, latin_bottom: int, latin_top: int, digit_bottom: int, digit_top: int, extreme_metrics: bool = False) -> None:
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    digits = "0123456789"
    letter_names = {character: f"uni{ord(character):04X}" for character in letters}
    digit_names = {character: f"uni{ord(character):04X}" for character in digits}
    cjk_names = {"中": "uni4E2D", "国": "uni56FD", "永": "uni6C38"}
    glyph_order = [".notdef", "space", *letter_names.values(), *digit_names.values(), *cjk_names.values()]
    glyphs = {name: rectangle(50, 0, 550, 700) for name in glyph_order}
    glyphs[".notdef"] = rectangle(50, 0, 550, 700)
    glyphs["space"] = TTGlyphPen(None).glyph()
    for name in letter_names.values():
        glyphs[name] = rectangle(70, latin_bottom, 530, latin_top)
    for name in digit_names.values():
        glyphs[name] = rectangle(90, digit_bottom, 510, digit_top)
    for name in cjk_names.values():
        glyphs[name] = rectangle(40, -80, 960, 880)
    cmap = {ord(character): name for character, name in {**letter_names, **digit_names, **cjk_names}.items()}
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder(glyph_order)
    fb.setupCharacterMap(cmap)
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics({name: (1000 if name in cjk_names.values() else 620, 40) for name in glyph_order})
    fb.setupHorizontalHeader(ascent=1200 if extreme_metrics else 900, descent=-40 if extreme_metrics else -220, lineGap=180 if extreme_metrics else 0)
    fb.setupOS2(sTypoAscender=1200 if extreme_metrics else 900, sTypoDescender=-40 if extreme_metrics else -220, sTypoLineGap=180 if extreme_metrics else 0, usWinAscent=1300, usWinDescent=100)
    fb.setupNameTable({"familyName": "MetricsTest", "styleName": "Regular", "uniqueFontIdentifier": "MetricsTest Regular", "fullName": "MetricsTest Regular", "psName": "MetricsTest-Regular"})
    fb.setupPost()
    fb.setupMaxp()
    fb.save(path)


def bounds(font: TTFont, character: str):
    glyph_set = font.getGlyphSet(); glyph_name = font.getBestCmap()[ord(character)]
    pen = BoundsPen(glyph_set); glyph_set[glyph_name].draw(pen)
    assert pen.bounds is not None
    return pen.bounds


with tempfile.TemporaryDirectory() as directory:
    temp = Path(directory)
    source = temp / "source.ttf"; normalized = temp / "normalized.ttf"
    make_font(source, 0, 700, 0, 700, extreme_metrics=True)
    normalize_path(source, normalized)
    font = TTFont(normalized)
    try:
        assert font["hhea"].ascent == 928
        assert font["hhea"].descent == -244
        assert font["hhea"].lineGap == 0
        assert font["OS/2"].sTypoAscender == font["hhea"].ascent
        assert font["OS/2"].sTypoDescender == font["hhea"].descent
        assert font["OS/2"].sTypoLineGap == 0
        assert font["OS/2"].fsSelection & (1 << 7)
    finally:
        font.close()

    # Different glyph extremes must still emit exactly the same TextView/EditText baseline contract.
    source_two = temp / "source-two.ttf"; normalized_two = temp / "normalized-two.ttf"
    make_font(source_two, -180, 1040, -120, 960, extreme_metrics=False)
    normalize_path(source_two, normalized_two)
    font_two = TTFont(normalized_two)
    try:
        assert font_two["hhea"].ascent == 928
        assert font_two["hhea"].descent == -244
        assert font_two["OS/2"].sTypoAscender == 928
        assert font_two["OS/2"].sTypoDescender == -244
        # Win metrics must be capped at the line-box contract (0.98/0.35 em) so
        # includeFontPadding cannot inflate line height with glyph extremes.
        assert font_two["OS/2"].usWinAscent == 980
        assert font_two["OS/2"].usWinDescent == 244
    finally:
        font_two.close()

    base = temp / "base.ttf"; latin = temp / "latin.ttf"; digit = temp / "digit.ttf"; output = temp / "composite.ttf"
    make_font(base, 0, 700, 0, 700)
    make_font(latin, 180, 980, 180, 980)
    make_font(digit, 150, 900, 150, 900)
    build(SimpleNamespace(cjk=str(base), latin=str(latin), digit=str(digit), output=str(output), weight=400, cjk_face=None, latin_face=None, digit_face=None, progress=None))
    composite = TTFont(output)
    try:
        a = bounds(composite, "A"); one = bounds(composite, "1")
        assert abs(a[1]) <= 20, a
        assert 650 <= a[3] - a[1] <= 760, a
        assert abs(one[1]) <= 20, one
        assert 650 <= one[3] - one[1] <= 760, one
        assert composite["hhea"].lineGap == 0
        assert composite["OS/2"].fsSelection & (1 << 7)
    finally:
        composite.close()

print("Font metrics and mixed-script baseline normalization passed.")
