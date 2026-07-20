#!/usr/bin/env python3
"""Extract safe UI font targets from Android font configuration XML files."""

from __future__ import annotations

import argparse
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

FONT_EXTENSIONS = (".ttf", ".otf", ".ttc")
EXACT_FAMILIES = {
    "sans-serif",
    "sans-serif-condensed",
    "roboto",
    "roboto-flex",
    "miui",
    "mipro",
    "google-sans",
    "google-sans-text",
    "source-sans-pro",
}


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def is_ui_family(name: str) -> bool:
    normalized = name.strip().lower().replace("_", "-")
    if normalized in EXACT_FAMILIES:
        return True
    if normalized.startswith(("google-sans", "roboto-", "miui-", "mipro-")):
        return True
    return False


def clean_filename(raw: str | None) -> str | None:
    if not raw:
        return None
    value = raw.strip().splitlines()[0].strip()
    if not value:
        return None
    value = os.path.basename(value)
    if not value.lower().endswith(FONT_EXTENSIONS):
        return None
    lowered = value.lower()
    if any(token in lowered for token in ("emoji", "symbol", "icons", "clock", "mono", "serif")):
        return None
    return value


def parse_weight(raw: str | None) -> int:
    try:
        value = int(raw or "400")
    except ValueError:
        value = 400
    return min(1000, max(1, value))


def extract_from_file(path: Path) -> list[tuple[str, int, str]]:
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        return []

    targets: list[tuple[str, int, str]] = []
    for family in root.iter():
        if local_name(family.tag) != "family":
            continue
        family_name = family.attrib.get("name", "").strip()
        if not family_name or not is_ui_family(family_name):
            continue
        for child in family:
            if local_name(child.tag) != "font":
                continue
            filename = clean_filename(child.text)
            if not filename:
                continue
            targets.append((filename, parse_weight(child.attrib.get("weight")), family_name))
    return targets


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("xml", nargs="+")
    args = parser.parse_args(argv)

    seen: set[str] = set()
    for raw_path in args.xml:
        path = Path(raw_path)
        if not path.is_file():
            continue
        for filename, weight, family in extract_from_file(path):
            if filename in seen:
                continue
            seen.add(filename)
            print(f"{filename}|{weight}|{family}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
