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
    "oplus-os-ui", "oplusosui", "coloros-sans", "oneplus-sans", "realme-sans", "vivo-sans", "vivosans",
    "vivo-sans-vf", "origin", "originos", "origin-sans", "originos-sans",
    "iqoo-sans", "iqoosans", "flyme", "flyme-sans", "flyme-ui", "flymesans",
    "flymefont", "meizu", "meizu-sans", "meizusans", "mflyme", "mflyme-sans",
    "honor-sans", "harmonyos-sans",
}
SAFE_PREFIXES = (
    "sans-serif-", "roboto-", "google-sans-", "source-sans-", "noto-sans-",
    "miui-", "mipro-", "misans-", "mi-sans-", "sysfont-", "sys-font-",
    "sys-sans-", "op-sans-", "oplus-sans-", "oppo-sans-", "opposans-",
    "oplus-os-ui-", "oplusosui-", "coloros-sans-", "oneplus-sans-", "realme-sans-", "vivo-sans-", "vivosans-",
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


# The overlay owns family classification. Keeping a second copy of the vendor lists here meant the
# slot-alias discovery and the XML rewrite could disagree about what counts as a UI family, and a
# name added to one was silently missing from the other.
try:
    from font_config_overlay import (
        effective_family_name as _overlay_effective_family_name,
        is_protected_file as _overlay_is_protected_file,
        is_safe_family as _overlay_is_safe_family,
        is_safe_mono_family as _overlay_is_safe_mono_family,
    )
except ImportError:  # pragma: no cover - only when the two files are separated
    _overlay_effective_family_name = None
    _overlay_is_protected_file = None
    _overlay_is_safe_family = None
    _overlay_is_safe_mono_family = None


def family_role(element: ET.Element, name: str) -> str | None:
    name = normalize(name)
    if not name:
        return None
    # Families carrying a locale/script contract are fallbacks, not the global UI family.
    for key in ("lang", "variant", "fallbackFor", "fallbackfor"):
        if element.attrib.get(key):
            return None
    if _overlay_is_safe_mono_family is not None and _overlay_is_safe_mono_family(name):
        return "mono"
    if any(token in name for token in PROTECTED_FAMILY_TOKENS):
        return None
    if _overlay_is_safe_family is not None:
        return "ui" if _overlay_is_safe_family(name) else None
    return "ui" if name in SAFE_EXACT_FAMILIES or name.startswith(SAFE_PREFIXES) else None


def protected_file(value: str, role: str = "ui") -> bool:
    if _overlay_is_protected_file is not None:
        return _overlay_is_protected_file(value, mono=role == "mono")
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
    root = tree.getroot()
    parents = {child: parent for parent in root.iter() for child in list(parent)}
    found: dict[tuple[str, int, str], dict[str, object]] = {}
    for family in tree.getroot().iter():
        if local_name(family.tag) != "family":
            continue
        family_name = (
            _overlay_effective_family_name(family, parents)
            if _overlay_effective_family_name is not None
            else family.attrib.get("name", "")
        )
        role = family_role(family, family_name)
        if role is None:
            continue
        parent = parents.get(family)
        if parent is not None and local_name(parent.tag) == "family-list":
            if any(parent.attrib.get(key) for key in ("lang", "variant", "fallbackFor", "fallbackfor")):
                continue
        for font in list(family):
            if local_name(font.tag) != "font" or not font.text:
                continue
            if font.attrib.get("style", "normal").lower() in {"italic", "oblique"}:
                continue
            filename = os.path.basename(font.text.strip())
            if protected_file(filename, role=role):
                continue
            weight = nearest_weight(font.attrib.get("weight"))
            found[(filename, weight, role)] = {
                "filename": filename,
                "weight": weight,
                "family": family_name,
                "role": role,
            }
    return sorted(found.values(), key=lambda item: (str(item["filename"]).lower(), int(item["weight"])))


def run_batch(job_file: Path) -> int:
    """Scan every listed document in one interpreter.

    Slot discovery used to pay a full embedded-CPython start per ROM document, so a device shipping
    eight font configuration files spent eight interpreter startups here before any font was even
    touched. Emits one tab separated line per target:
        TARGET<TAB>input<TAB>filename<TAB>weight<TAB>family<TAB>role
    and one status line per document:
        DOC<TAB>input<TAB>ok|error<TAB>count<TAB>message
    """
    for raw in job_file.read_text(encoding="utf-8").splitlines():
        source = raw.strip()
        if not source:
            continue
        try:
            entries = discover(Path(source))
        except (OSError, ET.ParseError, ValueError) as error:
            message = (str(error) or error.__class__.__name__).replace("\n", " ")
            print(f"DOC\t{source}\terror\t0\t{message}")
            continue
        for entry in entries:
            print(
                f"TARGET\t{source}\t{entry['filename']}\t{entry['weight']}\t"
                f"{entry['family']}\t{entry['role']}"
            )
        print(f"DOC\t{source}\tok\t{len(entries)}\t")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path)
    parser.add_argument("--batch", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.batch is not None:
        try:
            return run_batch(args.batch)
        except OSError as error:
            print(json.dumps({"status": "error", "message": str(error)}, ensure_ascii=False, separators=(",", ":")))
            return 2
    if args.input is None:
        parser.error("--input is required unless --batch is used")
    try:
        targets = discover(args.input)
        if args.json:
            print(json.dumps({"status": "ok", "targets": targets}, ensure_ascii=False, separators=(",", ":")))
        else:
            for target in targets:
                print(f"{target['filename']}|{target['weight']}|{target['family']}|{target['role']}")
        return 0
    except (OSError, ET.ParseError, ValueError) as error:
        if args.json:
            print(json.dumps({"status": "error", "message": str(error)}, ensure_ascii=False, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
