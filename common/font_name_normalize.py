#!/usr/bin/env python3
"""Normalize generated LuoShu UI font identity without changing glyph geometry.

Android's system font map is keyed by XML family names, but framework caches, OEM aliases and some
native clients also retain the sfnt Family, Typographic Family and PostScript names. Every generated
static weight therefore receives one deterministic LuoShu identity before it is referenced by the
no-Hook XML overlay.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import tempfile
from pathlib import Path

from fontTools.ttLib import TTFont, TTLibError

WEIGHT_NAMES = {
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
NAME_IDS = {
    1: "family",
    2: "subfamily",
    3: "unique",
    4: "full",
    6: "postscript",
    16: "family",
    17: "subfamily",
    21: "family",
    22: "subfamily",
}


def nearest_weight(value: int) -> int:
    value = min(1000, max(1, value))
    return min(WEIGHT_NAMES, key=lambda weight: abs(weight - value))


def set_name(name_table, name_id: int, value: str) -> None:
    # Windows Unicode English and Macintosh Roman English cover Android/fontTools readers while
    # avoiding an unbounded copy of stale localized family names.
    name_table.setName(value, name_id, 3, 1, 0x0409)
    try:
        value.encode("mac_roman")
    except UnicodeEncodeError:
        return
    name_table.setName(value, name_id, 1, 0, 0)


def normalize_font(font: TTFont, weight: int, family: str, source_digest: str) -> None:
    if "name" not in font:
        raise ValueError("font has no name table")

    role = WEIGHT_NAMES[weight]
    family = family.strip() or "LuoShu UI"
    postscript_family = "".join(character for character in family if character.isalnum()) or "LuoShuUI"
    values = {
        "family": family,
        "subfamily": role,
        "unique": f"{family};{role};{source_digest[:12]}",
        "full": family if role == "Regular" else f"{family} {role}",
        "postscript": f"{postscript_family}-{role}",
    }
    for name_id, key in NAME_IDS.items():
        set_name(font["name"], name_id, values[key])

    if "OS/2" in font:
        os2 = font["OS/2"]
        os2.usWeightClass = weight
        # Clear REGULAR/BOLD/ITALIC before applying the generated upright static role.
        os2.fsSelection &= ~((1 << 0) | (1 << 5) | (1 << 6))
        if weight == 400:
            os2.fsSelection |= 1 << 6
        if weight >= 700:
            os2.fsSelection |= 1 << 5
    if "head" in font:
        font["head"].macStyle &= ~0b11
        if weight >= 700:
            font["head"].macStyle |= 0b1

    # Keep CFF metadata consistent with the sfnt name table when present.
    if "CFF " in font:
        cff = font["CFF "].cff
        top = cff.topDictIndex[0]
        top.FamilyName = family
        top.FullName = values["full"]
        top.Weight = role
        cff.fontNames = [values["postscript"]]


def atomic_save(font: TTFont, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    os.close(descriptor)
    try:
        font.save(temporary, reorderTables=False)
        if os.path.getsize(temporary) < 1024:
            raise ValueError("normalized font is unexpectedly small")
        os.chmod(temporary, 0o644)
        os.replace(temporary, output)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--weight", required=True, type=int)
    parser.add_argument("--family", default="LuoShu UI")
    args = parser.parse_args()

    weight = nearest_weight(args.weight)
    try:
        digest = hashlib.sha256(args.input.read_bytes()).hexdigest()
        font = TTFont(args.input, lazy=False, recalcTimestamp=False)
        try:
            normalize_font(font, weight, args.family, digest)
            atomic_save(font, args.output)
        finally:
            font.close()
        return 0
    except (OSError, TTLibError, ValueError) as error:
        args.output.unlink(missing_ok=True)
        print(f"font identity normalization failed: {error}", file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
