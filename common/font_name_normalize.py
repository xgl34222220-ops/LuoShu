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

from font_metrics_normalize import normalize_font_metrics

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


def normalize_font(font: TTFont, weight: int, family: str, source_digest: str, monospaced: bool = False) -> None:
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

    normalize_font_metrics(font, monospaced=monospaced)


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


def _normalize_one(source: Path, output: Path, weight: int, family: str, monospace: bool) -> None:
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    font = TTFont(source, lazy=False, recalcTimestamp=False)
    try:
        normalize_font(font, nearest_weight(weight), family, digest, monospaced=monospace)
        atomic_save(font, output)
    finally:
        font.close()


def run_batch(job_file: Path) -> int:
    """Normalize several weights in one interpreter.

    Preparing the nine static weights called this script nine times, and each call paid a full
    embedded-CPython start. On a phone that start costs far more than the normalization itself.

    Job lines are tab separated:  input<TAB>output<TAB>weight<TAB>family<TAB>monospace(0|1)
    Result lines:                 output<TAB>ok|error<TAB>message
    """
    for raw in job_file.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip("\n")
        if not line.strip():
            continue
        fields = line.split("\t")
        if len(fields) < 3:
            print(f"\terror\tmalformed job line")
            continue
        source, output, weight = Path(fields[0]), Path(fields[1]), fields[2]
        family = fields[3] if len(fields) > 3 and fields[3] else "LuoShu UI"
        monospace = len(fields) > 4 and fields[4] == "1"
        try:
            _normalize_one(source, output, int(weight or 400), family, monospace)
        except (OSError, TTLibError, ValueError) as error:
            output.unlink(missing_ok=True)
            message = (str(error) or error.__class__.__name__).replace("\n", " ").replace("\t", " ")
            print(f"{output}\terror\t{message}")
            continue
        print(f"{output}\tok\t")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--batch", type=Path)
    parser.add_argument("--weight", type=int, default=400)
    parser.add_argument("--family", default="LuoShu UI")
    parser.add_argument("--monospace", action="store_true")
    args = parser.parse_args()

    if args.batch is not None:
        try:
            return run_batch(args.batch)
        except OSError as error:
            print(f"font identity normalization batch failed: {error}", file=os.sys.stderr)
            return 2
    if args.input is None or args.output is None:
        parser.error("--input/--output are required unless --batch is used")

    weight = nearest_weight(args.weight)
    try:
        digest = hashlib.sha256(args.input.read_bytes()).hexdigest()
        font = TTFont(args.input, lazy=False, recalcTimestamp=False)
        try:
            normalize_font(font, weight, args.family, digest, monospaced=args.monospace)
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
