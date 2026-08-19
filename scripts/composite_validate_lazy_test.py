#!/usr/bin/env python3
"""The composite's own validation must not decompile the whole font.

_validate_output reads the cmap, draws 中/A/1 and reads maxp. Opening the freshly written composite
with lazy=False expanded every glyph of what is a ~20 MB CJK font on a real device, purely to look
at three of them. That cost shows up on every switch and inflates the peak resident set that users
reported alongside the 100% CPU process.
"""
from __future__ import annotations

import inspect
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "common"))

import composite_font


def main() -> int:
    source = inspect.getsource(composite_font._validate_output)
    assert "lazy=True" in source, "_validate_output 必须惰性打开字体"
    assert "lazy=False" not in source, "_validate_output 不得整体展开字形"

    # And it must still actually validate: a font missing a required role has to be rejected.
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen

    def build(path: Path, codepoints: list[int]) -> None:
        order = [".notdef"] + [f"u{c:04X}" for c in codepoints]
        fb = FontBuilder(1000, isTTF=True)
        fb.setupGlyphOrder(order)
        fb.setupCharacterMap({c: f"u{c:04X}" for c in codepoints})
        glyphs, metrics = {}, {}
        for name in order:
            pen = TTGlyphPen(None)
            if name != ".notdef":
                pen.moveTo((50, 0)); pen.lineTo((550, 0)); pen.lineTo((550, 700)); pen.lineTo((50, 700))
                pen.closePath()
            glyphs[name] = pen.glyph()
            metrics[name] = (600, 50)
        fb.setupGlyf(glyphs)
        fb.setupHorizontalMetrics(metrics)
        fb.setupHorizontalHeader(ascent=800, descent=-200)
        fb.setupNameTable({"familyName": "Probe", "styleName": "Regular", "psName": "Probe-Regular"})
        fb.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
        fb.setupPost()
        fb.save(str(path))

    with tempfile.TemporaryDirectory() as tmp:
        good = Path(tmp) / "good.ttf"
        build(good, [ord("中"), ord("A"), ord("1")])
        report = composite_font._validate_output(good)
        assert report["glyphs"] == 4, report
        assert set(report["bounds"]) == {"cjk", "latin", "digit"}, report

        # Missing the digit role must still be caught, lazily or not.
        bad = Path(tmp) / "bad.ttf"
        build(bad, [ord("中"), ord("A")])
        try:
            composite_font._validate_output(bad)
        except composite_font.CompositeError:
            pass
        else:
            raise AssertionError("缺少数字字形的复合字体本应被拒绝")

    print("Composite validation lazy-load tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
