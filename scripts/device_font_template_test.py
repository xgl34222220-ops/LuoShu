#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "common"))
import device_font_template as mod


def rect(width: int, y_min: int, y_max: int):
    pen = TTGlyphPen(None)
    pen.moveTo((40, y_min))
    pen.lineTo((width - 40, y_min))
    pen.lineTo((width - 40, y_max))
    pen.lineTo((40, y_max))
    pen.closePath()
    return pen.glyph()


def build_font(path: Path, family: str, postscript: str, weight: int, ascent: int, descent: int) -> None:
    glyph_order = [".notdef", "H", "x", "zero", "one", "uni4E2D", "parenleft", "percent"]
    cmap = {
        ord("H"): "H",
        ord("x"): "x",
        ord("0"): "zero",
        ord("1"): "one",
        ord("中"): "uni4E2D",
        ord("("): "parenleft",
        ord("%"): "percent",
    }
    glyphs = {
        ".notdef": rect(600, 0, 700),
        "H": rect(620, 0, 720),
        "x": rect(560, 0, 500),
        "zero": rect(600, -10, 700),
        "one": rect(540, 0, 700),
        "uni4E2D": rect(1000, -80, 880),
        "parenleft": rect(360, -120, 760),
        "percent": rect(720, -20, 710),
    }
    metrics = {name: ((1000 if name == "uni4E2D" else 620), 20) for name in glyph_order}
    builder = FontBuilder(1000, isTTF=True)
    builder.setupGlyphOrder(glyph_order)
    builder.setupCharacterMap(cmap)
    builder.setupGlyf(glyphs)
    builder.setupHorizontalMetrics(metrics)
    builder.setupHorizontalHeader(ascent=ascent, descent=descent, lineGap=12)
    builder.setupNameTable({
        "familyName": family,
        "styleName": "Regular",
        "uniqueFontIdentifier": f"{family} Regular",
        "fullName": f"{family} Regular",
        "psName": postscript,
        "version": "Version 1.000",
    })
    builder.setupOS2(
        sTypoAscender=ascent - 10,
        sTypoDescender=descent + 10,
        sTypoLineGap=8,
        usWinAscent=ascent + 40,
        usWinDescent=abs(descent) + 40,
        sxHeight=500,
        sCapHeight=720,
        usWeightClass=weight,
        usWidthClass=5,
    )
    builder.setupPost()
    builder.setupMaxp()
    path.parent.mkdir(parents=True, exist_ok=True)
    builder.save(path)


def main() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        system_font = root / "system/fonts/Roboto-Regular.ttf"
        dynamic_font = root / "data/fonts/files/hash/GoogleSans-Regular.ttf"
        emoji_font = root / "system/fonts/NotoColorEmoji.ttf"
        build_font(system_font, "Roboto", "Roboto-Regular", 400, 930, -250)
        build_font(dynamic_font, "Google Sans", "GoogleSans-Regular", 400, 950, -270)
        build_font(emoji_font, "Noto Color Emoji", "NotoColorEmoji", 400, 1000, -300)

        system_xml = root / "system/etc/fonts.xml"
        system_xml.parent.mkdir(parents=True, exist_ok=True)
        system_xml.write_text(
            """<?xml version='1.0' encoding='utf-8'?>
<familyset>
  <family name='sans-serif'><font weight='400' style='normal'>Roboto-Regular.ttf</font></family>
  <family name='emoji-family'><font weight='400' style='normal'>NotoColorEmoji.ttf</font></family>
</familyset>
""",
            encoding="utf-8",
        )
        data_xml = root / "data/fonts/config/config.xml"
        data_xml.parent.mkdir(parents=True, exist_ok=True)
        data_xml.write_text(
            """<?xml version='1.0' encoding='utf-8'?>
<fontConfig>
  <lastModifiedDate value='1'/>
  <updatedFontDir value='hash'/>
  <family name='google-sans'><font name='GoogleSans-Regular' weight='400' style='normal'/></family>
</fontConfig>
""",
            encoding="utf-8",
        )

        payload = mod.build_template(
            [system_xml, data_xml],
            [root / "system/fonts", root / "data/fonts/files"],
            "fixture-build",
        )
        assert payload["schema"] == "device-font-template-v1"
        assert payload["summary"]["slots"] == 3, payload["summary"]
        assert payload["summary"]["resolved"] == 3, payload["summary"]
        slots = {(slot["familyNormalized"], slot["weight"]): slot for slot in payload["slots"]}
        ui = slots[("sans-serif", 400)]
        assert ui["replaceable"] is True
        assert "global-ui" in ui["roles"]
        assert ui["font"]["metrics"]["hheaAscent"] == 930
        assert ui["font"]["metrics"]["hheaDescent"] == -250
        assert ui["font"]["probes"]["digits"]["hits"] == 2
        dynamic = slots[("google-sans", 400)]
        assert "dynamic" in dynamic["roles"]
        assert dynamic["resolvedPath"].endswith("GoogleSans-Regular.ttf")
        emoji = slots[("emoji-family", 400)]
        assert emoji["replaceable"] is False
        assert "protected" in emoji["roles"]
        print(json.dumps(payload["summary"], ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
