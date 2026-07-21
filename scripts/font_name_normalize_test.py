#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont


def bounds(font: TTFont, character: str):
    name = (font.getBestCmap() or {})[ord(character)]
    pen = BoundsPen(font.getGlyphSet())
    font.getGlyphSet()[name].draw(pen)
    return pen.bounds


def debug_name(font: TTFont, name_id: int) -> str:
    return font["name"].getDebugName(name_id) or ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--font", required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]

    with tempfile.TemporaryDirectory(prefix="luoshu-name-") as directory:
        output = Path(directory) / "LuoShu-700.ttf"
        subprocess.run(
            [
                "python3",
                str(root / "common" / "font_name_normalize.py"),
                "--input",
                str(args.font),
                "--output",
                str(output),
                "--weight",
                "700",
                "--family",
                "LuoShu UI",
            ],
            check=True,
        )
        source = TTFont(args.font, lazy=False, recalcTimestamp=False)
        result = TTFont(output, lazy=False, recalcTimestamp=False)
        try:
            assert result["maxp"].numGlyphs == source["maxp"].numGlyphs
            assert bounds(result, "A") == bounds(source, "A")
            assert bounds(result, "0") == bounds(source, "0")
            assert result["hmtx"].metrics[(result.getBestCmap() or {})[ord("A")]] == \
                source["hmtx"].metrics[(source.getBestCmap() or {})[ord("A")]]

            assert debug_name(result, 1) == "LuoShu UI"
            assert debug_name(result, 2) == "Bold"
            assert debug_name(result, 4) == "LuoShu UI Bold"
            assert debug_name(result, 6) == "LuoShuUI-Bold"
            assert debug_name(result, 16) == "LuoShu UI"
            assert debug_name(result, 17) == "Bold"
            assert result["OS/2"].usWeightClass == 700
            assert result["OS/2"].fsSelection & (1 << 5)
            assert result["head"].macStyle & 0b1
        finally:
            source.close()
            result.close()

    print("Font identity normalization tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
