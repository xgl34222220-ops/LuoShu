#!/usr/bin/env python3
"""Discover every boot-safe UI font file referenced by an Android font XML.

The scanner deliberately ignores locale/script fallbacks and protected families.  Its output is used
to materialize file-slot aliases in the same partition as the original XML, so OEM additions do not
need to be hard-coded one model at a time.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

SAFE_EXACT_FAMILIES = {
    "sans", "sans-serif", "sans-serif-condensed", "default", "default-sans",
    "system-ui", "ui-sans-serif", "roboto", "roboto-flex", "roboto-static",
    "google-sans", "google-sans-text", "google-sans-flex", "source-sans",
    "source-sans-pro", "noto-sans", "noto-sans-cjk", "miui", "mipro",
    "misans", "mi-sans", "sysfont", "sys-font", "sys-sans", "sys-sans-en",
    "op-sans", "op-sans-en", "oplus-sans", "oppo-sans", "opposans",
    "coloros-sans", "oneplus-sans", "realme-sans", "vivo-sans", "vivosans",
    "vivo-sans-vf", "origin", "originos", "origin-sans", "originos-sans",
    "iqoo-sans", "iqoosans", "flyme", "flyme-sans", "flyme-ui", "flymesans",
    "flymefont", "meizu", "meizu-sans", "meizusans", "mflyme", "mflyme-sans",
    "honor-sans", "harmonyos-sans",
}
SAFE_PREFIXES = (
    "sans-serif-", "roboto-", "google-sans-", "source-sans-", "noto-sans-",
    "miui-", "mipro-", "misans-", "mi-sans-", "sysfont-", "sys-font-",
    "sys-sans-", "op-sans-", "oplus-sans-", "oppo-sans-", "opposans-",
    "coloros-sans-", "oneplus-sans-", "realme-sans-", "vivo-sans-", "vivosans-",
    "origin-sans-", "originos-sans-", "iqoo-sans-", "iqoosans-", "flyme-sans-",
    "flymesans-", "flymefont-", "meizu-sans-", "meizusans-", "mflyme-",
    "honor-sans-", "harmonyos-sans-",
)
PROTECTED_FAMILY_TOKENS = (
    "emoji", "symbol", "icon", "material", "dingbat", "mono",
    "clock", "mitype", "math", "music", "braille", "barcode", "qrcode",
    "fallback", "legacy",
)
PROTECTED_FILE_TOKENS = PROTECTED_FAMILY_TOKENS + ("serif",)
FONT_SUFFIXES = (".ttf", ".otf", ".ttc")
WEIGHTS = (100, 200, 300, 400, 500, 600, 700, 800, 900)


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def normalize(value: str) -> str:
    return re.sub(r"[\s_-]+", "-", value.strip().lower()).strip("-")


def safe_family(element: ET.Element) -> bool:
    name = normalize(element.attrib.get("name", ""))
    if not name or any(token in name for token in PROTECTED_FAMILY_TOKENS):
        return False
    # Families carrying a locale/script contract are fallbacks, not the global UI family.
    for key in ("lang", "variant", "fallbackFor", "fallbackfor"):
        if element.attrib.get(key):
            return False
    return name in SAFE_EXACT_FAMILIES or name.startswith(SAFE_PREFIXES)


def protected_file(value: str) -> bool:
    filename = os.path.basename(value.strip()).lower()
    return (
        not filename.endswith(FONT_SUFFIXES)
        or any(token in filename for token in PROTECTED_FILE_TOKENS)
    )


def nearest_weight(raw: str | None) -> int:
    try:
        requested = int(raw or "400")
    except ValueError:
        requested = 400
    return min(WEIGHTS, key=lambda item: abs(item - max(1, min(1000, requested))))


def discover(path: Path) -> list[dict[str, object]]:
    tree = ET.parse(path)
    found: dict[tuple[str, int], dict[str, object]] = {}
    for family in tree.getroot().iter():
        if local_name(family.tag) != "family" or not safe_family(family):
            continue
        family_name = family.attrib.get("name", "")
        for font in list(family):
            if local_name(font.tag) != "font" or not font.text:
                continue
            if font.attrib.get("style", "normal").lower() in {"italic", "oblique"}:
                continue
            filename = os.path.basename(font.text.strip())
            if protected_file(filename):
                continue
            weight = nearest_weight(font.attrib.get("weight"))
            found[(filename, weight)] = {
                "filename": filename,
                "weight": weight,
                "family": family_name,
            }
    return sorted(found.values(), key=lambda item: (str(item["filename"]).lower(), int(item["weight"])))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        targets = discover(args.input)
        if args.json:
            print(json.dumps({"status": "ok", "targets": targets}, ensure_ascii=False, separators=(",", ":")))
        else:
            for target in targets:
                print(f"{target['filename']}|{target['weight']}|{target['family']}")
        return 0
    except (OSError, ET.ParseError, ValueError) as error:
        if args.json:
            print(json.dumps({"status": "error", "message": str(error)}, ensure_ascii=False, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
