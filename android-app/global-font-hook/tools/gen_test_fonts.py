# Generates the tiny synthetic test fonts used by the instrumented tests (no third-party glyphs).
import sys
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

def box(w):
    p = TTGlyphPen(None)
    p.moveTo((50, 0)); p.lineTo((50, 600)); p.lineTo((w - 50, 600)); p.lineTo((w - 50, 0)); p.closePath()
    return p.glyph()

def build(path, family, cps, fixed, widths):
    names = [".notdef", "space"] + ["u%04X" % c for c in cps]
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder(names)
    cmap = {0x20: "space"}
    cmap.update({c: "u%04X" % c for c in cps})
    fb.setupCharacterMap(cmap)
    glyphs = {n: box(widths(n)) for n in names}
    glyphs["space"] = TTGlyphPen(None).glyph()
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics({n: (widths(n), 50) for n in names})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({"familyName": family, "styleName": "Regular"})
    fb.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
    fb.setupPost(isFixedPitch=1 if fixed else 0)
    fb.save(path)

latin = list(range(0x30, 0x3A)) + list(range(0x41, 0x5B)) + list(range(0x61, 0x7B))
out = sys.argv[1]
prop = lambda n: 300 if n in ("u0069", "u006C", "space") else (900 if n == "u0057" else 560)
build(out + "/luoshu_body.ttf", "LuoShu Test Text", latin, False, prop)
build(out + "/luoshu_icons.ttf", "x9", latin + list(range(0xE000, 0xE100)), False, lambda n: 1000)
build(out + "/luoshu_mono.ttf", "x8", latin, True, lambda n: 600)
