#!/usr/bin/env python3
"""Rewrite generated font family/subfamily metadata without changing glyph outlines."""
from __future__ import annotations

import argparse
import os
import re
import tempfile
from pathlib import Path

from fontTools.ttLib import TTFont


def subfamily_for_weight(weight: int) -> str:
    names = {
        100: "Thin",
        200: "ExtraLight",
        300: "Light",
        400: "Regular",
        500: "Medium",
        600: "SemiBold",
        700: "Bold",
        800: "ExtraBold",
        900: "Black",
    }
    return names.get(weight, f"Weight{weight}")


def replace_name(font: TTFont, name_id: int, value: str) -> None:
    table = font["name"]
    for record in table.names:
        if record.nameID != name_id:
            continue
        try:
            record.string = value.encode(record.getEncoding(), errors="replace")
        except Exception:
            record.string = value.encode("utf-16-be")
    # Ensure common Windows Unicode English records exist.
    table.setName(value, name_id, 3, 1, 0x409)
    table.setName(value, name_id, 1, 0, 0)


def rewrite(source: Path, output: Path, family: str, weight: int) -> None:
    font = TTFont(str(source), lazy=False, recalcTimestamp=False, recalcBBoxes=True)
    try:
        subfamily = subfamily_for_weight(weight)
        postscript_family = re.sub(r"[^A-Za-z0-9]", "", family) or "LuoShuFont"
        postscript = f"{postscript_family}-{subfamily}"
        replace_name(font, 1, family)
        replace_name(font, 2, subfamily)
        replace_name(font, 4, f"{family} {subfamily}")
        replace_name(font, 6, postscript)
        replace_name(font, 16, family)
        replace_name(font, 17, subfamily)
        if "OS/2" in font:
            font["OS/2"].usWeightClass = max(1, min(1000, int(weight)))
            font["OS/2"].fsSelection &= ~0x20
            font["OS/2"].fsSelection &= ~0x40
            if weight >= 700:
                font["OS/2"].fsSelection |= 0x20
            elif weight == 400:
                font["OS/2"].fsSelection |= 0x40
        if "head" in font:
            if weight >= 700:
                font["head"].macStyle |= 0x01
            else:
                font["head"].macStyle &= ~0x01
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(prefix=output.name + ".", suffix=".tmp", dir=output.parent, delete=False) as handle:
            temporary = Path(handle.name)
        try:
            font.save(str(temporary), reorderTables=False)
            os.chmod(temporary, 0o644)
            os.replace(temporary, output)
        finally:
            temporary.unlink(missing_ok=True)
    finally:
        font.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input")
    parser.add_argument("output")
    parser.add_argument("--family", required=True)
    parser.add_argument("--weight", type=int, required=True)
    args = parser.parse_args()
    rewrite(Path(args.input), Path(args.output), args.family, args.weight)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
