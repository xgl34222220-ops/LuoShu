#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
import composite_font as engine


def bounds(font: TTFont, character: str):
    cmap = font.getBestCmap() or {}
    name = cmap[ord(character)]
    pen = BoundsPen(font.getGlyphSet())
    font.getGlyphSet()[name].draw(pen)
    assert pen.bounds is not None, character
    return tuple(float(value) for value in pen.bounds)


def advance(font: TTFont, character: str) -> int:
    name = (font.getBestCmap() or {})[ord(character)]
    return int(font["hmtx"].metrics[name][0])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cjk", required=True)
    parser.add_argument("--latin", required=True)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    cjk_path = Path(args.cjk)
    latin_path = Path(args.latin)
    face = engine._pick_face(cjk_path, "cjk", 400, None)

    with tempfile.TemporaryDirectory(prefix="luoshu-align-") as directory:
        output = Path(directory) / "aligned.ttf"
        subprocess.run(
            [
                sys.executable,
                str(root / "common" / "composite_aligned.py"),
                "--cjk",
                str(cjk_path),
                "--latin",
                str(latin_path),
                "--digit",
                str(latin_path),
                "--output",
                str(output),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
        )

        base = TTFont(str(cjk_path), fontNumber=face, lazy=False, recalcTimestamp=False)
        source = TTFont(str(latin_path), lazy=False, recalcTimestamp=False)
        result = TTFont(str(output), lazy=False, recalcTimestamp=False)
        try:
            upem = float(result["head"].unitsPerEm)
            base_h = bounds(base, "H")
            result_h = bounds(result, "H")
            base_height = base_h[3] - base_h[1]
            result_height = result_h[3] - result_h[1]
            ratio = result_height / base_height
            assert 0.90 <= ratio <= 1.10, (base_h, result_h, ratio)
            assert abs(result_h[1] - base_h[1]) <= upem * 0.06, (base_h, result_h)

            # Vertical normalization must not widen launcher labels.
            expected_advance = round(
                advance(source, "H")
                * result["head"].unitsPerEm
                / source["head"].unitsPerEm
            )
            assert advance(result, "H") == expected_advance

            # The complete CJK base remains untouched.
            assert bounds(result, "中") == bounds(base, "中")
        finally:
            base.close()
            source.close()
            result.close()

    print("Composite geometry alignment tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
