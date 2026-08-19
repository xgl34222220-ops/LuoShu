#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "common"))

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib.tables._g_v_a_r import table__g_v_a_r
from fontTools.ttLib.tables.TupleVariation import TupleVariation
from fontTools.varLib import instancer

import device_font_slot_build_base as builder


def build_variable_font(path: Path, glyph_count: int = 40) -> None:
    order = [".notdef"] + [f"g{i}" for i in range(glyph_count)]
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap({0x4E00 + i: f"g{i}" for i in range(glyph_count)})
    glyphs, metrics = {}, {}
    for name in order:
        pen = TTGlyphPen(None)
        if name != ".notdef":
            pen.moveTo((60, 40)); pen.lineTo((320, 70)); pen.lineTo((260, 460)); pen.lineTo((100, 420)); pen.closePath()
        glyphs[name] = pen.glyph()
        metrics[name] = (1000, 60)
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=880, descent=-120)
    fb.setupNameTable({"familyName": "CacheVF", "styleName": "Regular", "psName": "CacheVF-Regular"})
    fb.setupOS2(sTypoAscender=880, sTypoDescender=-120, usWinAscent=880, usWinDescent=120)
    fb.setupPost()
    fb.setupFvar([("wght", 100, 400, 900, "Weight")], [])
    gvar = table__g_v_a_r()
    gvar.version, gvar.reserved, gvar.variations = 1, 0, {}
    for name in order:
        if name == ".notdef":
            continue
        points = len(glyphs[name].coordinates) + 4
        gvar.variations[name] = [TupleVariation({"wght": (0, 1, 1)}, [(25, 25)] * points)]
    fb.font["gvar"] = gvar
    fb.save(str(path))


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "CacheVF.ttf"
        build_variable_font(source)
        calls = {"n": 0}
        original = instancer.instantiateVariableFont

        def counting(*args, **kwargs):
            calls["n"] += 1
            return original(*args, **kwargs)

        builder.instantiateVariableFont = counting
        builder._STATIC_INSTANCE_CACHE.clear()
        try:
            for _ in range(6):
                font = builder.read_source(source, -1, 400)
                assert "glyf" in font
                font.close()
            assert calls["n"] == 1, f"同源同字重应只实例化 1 次，实际 {calls['n']}"

            builder.read_source(source, -1, 700).close()
            assert calls["n"] == 2, f"不同字重应独立实例化，实际 {calls['n']}"

            before = source.stat()
            os.chmod(source, 0o600)
            os.utime(source, ns=(before.st_atime_ns, before.st_mtime_ns))
            builder.read_source(source, -1, 400).close()
            assert calls["n"] == 3, f"ctime 身份变化后必须失效，实际 {calls['n']}"

            build_variable_font(source, glyph_count=41)
            builder.read_source(source, -1, 400).close()
            assert calls["n"] == 4, f"源文件变化后必须重新实例化，实际 {calls['n']}"
        finally:
            builder.instantiateVariableFont = original
            builder._STATIC_INSTANCE_CACHE.clear()

        static = Path(tmp) / "Static.ttf"
        fb = FontBuilder(1000, isTTF=True)
        fb.setupGlyphOrder([".notdef", "a"])
        fb.setupCharacterMap({0x61: "a"})
        pen = TTGlyphPen(None)
        pen.moveTo((0, 0)); pen.lineTo((500, 0)); pen.lineTo((500, 700)); pen.lineTo((0, 700)); pen.closePath()
        fb.setupGlyf({".notdef": TTGlyphPen(None).glyph(), "a": pen.glyph()})
        fb.setupHorizontalMetrics({".notdef": (600, 0), "a": (600, 0)})
        fb.setupHorizontalHeader(ascent=800, descent=-200)
        fb.setupNameTable({"familyName": "Static", "styleName": "Regular", "psName": "Static-Regular"})
        fb.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800, usWinDescent=200)
        fb.setupPost()
        fb.save(str(static))
        builder._STATIC_INSTANCE_CACHE.clear()
        builder.read_source(static, -1, 400).close()
        assert not builder._STATIC_INSTANCE_CACHE, "静态字体不应进入实例缓存"

    print("Slot build variable-instance cache tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
