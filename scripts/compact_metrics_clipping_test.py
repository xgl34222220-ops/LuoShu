#!/usr/bin/env python3
"""The compact line box must never cut into text that is actually drawn.

HyperOS physical slots ask for a tight, fixed line contract. The old implementation reached that by
monkey-patching _outline_extremes to None from a shell heredoc, which told the normalizer to ignore
the font's real ink entirely, and capped hhea at 0.98em. A CJK face whose ink reaches past that cap
therefore had its overflow painted into the previous line (酷安标题压住热度) and its descenders
clipped (QQ 年龄标签少一截). ColorOS runs the standard path with a 1.60em cap, which is why the same
font behaved oppositely on the two devices.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "common"))
EMBEDDED_SITE = ROOT / "common/python/lib/python3.14/site-packages"
if EMBEDDED_SITE.is_dir():
    sys.path.insert(0, str(EMBEDDED_SITE))

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

import font_metrics_normalize as metrics

UPEM = 1000
CJK_TOP = 1050      # 1.05em: past the 0.98em compact cap
DESC_BOTTOM = -260  # 0.26em below the baseline
RARE_TOP = 1900     # one rare glyph with a long tail, outside the UI probe set


def build(path: Path) -> None:
    chars = "中文国永AaHhx0123456789gjpqy"
    order = [".notdef"] + [f"u{ord(c):04X}" for c in chars] + ["rare"]
    fb = FontBuilder(UPEM, isTTF=True)
    fb.setupGlyphOrder(order)
    fb.setupCharacterMap({**{ord(c): f"u{ord(c):04X}" for c in chars}, 0x2E80: "rare"})
    glyphs, hmtx = {}, {}
    for name in order:
        pen = TTGlyphPen(None)
        if name == "rare":
            top, bottom = RARE_TOP, -40
        elif name != ".notdef":
            char = chr(int(name[1:], 16))
            if char in "中文国永":
                top, bottom = CJK_TOP, -60
            elif char in "gjpqy":
                top, bottom = 520, DESC_BOTTOM
            else:
                top, bottom = 720, 0
        else:
            top = bottom = 0
        if name != ".notdef":
            pen.moveTo((60, bottom)); pen.lineTo((560, bottom))
            pen.lineTo((560, top)); pen.lineTo((60, top)); pen.closePath()
        glyphs[name] = pen.glyph()
        hmtx[name] = (620, 60)
    fb.setupGlyf(glyphs)
    fb.setupHorizontalMetrics(hmtx)
    fb.setupHorizontalHeader(ascent=880, descent=-120)
    fb.setupNameTable({"familyName": "Tall", "styleName": "Regular", "psName": "Tall-Regular"})
    fb.setupOS2(sTypoAscender=880, sTypoDescender=-120, usWinAscent=880, usWinDescent=120)
    fb.setupPost()
    fb.save(str(path))


def main() -> int:
    hyperos = (ROOT / "common/hyperos_global.sh").read_text(encoding="utf-8")
    assert "--compact" in hyperos, "HyperOS 物理槽必须调用正式 --compact 模式"
    assert "_outline_extremes = lambda font: None" not in hyperos, "旧 monkey-patch 不得回归"

    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "Tall.ttf"
        build(source)

        compact_out = Path(tmp) / "compact.ttf"
        metrics.normalize_path(source, compact_out, compact=True)
        font = TTFont(compact_out)
        ascent = int(font["hhea"].ascent)
        descent = int(font["hhea"].descent)

        assert ascent >= CJK_TOP, f"紧凑行框把中文墨迹削掉了 {CJK_TOP - ascent} 单位，会压进上一行"
        assert descent <= DESC_BOTTOM, f"紧凑行框把下伸部裁掉了 {DESC_BOTTOM - descent} 单位"
        assert int(font["OS/2"].usWinAscent) >= CJK_TOP, "usWinAscent 仍低于真实墨迹"
        assert int(font["OS/2"].usWinDescent) >= -DESC_BOTTOM, "usWinDescent 仍低于真实下伸"

        # Still compact: one rare long-tailed glyph outside the probe set must not inflate the box.
        assert ascent < RARE_TOP, "紧凑模式不应被探针集之外的极端字形撑大"

        standard_out = Path(tmp) / "standard.ttf"
        metrics.normalize_path(source, standard_out)
        std = TTFont(standard_out)
        assert int(std["hhea"].ascent) >= CJK_TOP, "标准路径本就应包住墨迹"

        # The compact box stays tighter than the standard one, which is the whole point of it.
        assert (ascent - descent) <= (int(std["hhea"].ascent) - int(std["hhea"].descent)) + UPEM // 10, \
            "紧凑行框不应比标准行框还宽"

        report = metrics.normalize_path(source, Path(tmp) / "r.ttf", compact=True)
        assert report["metricsSource"] == "compact", report

    print("Compact line-box clipping tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
