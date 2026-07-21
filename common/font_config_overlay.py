#!/usr/bin/env python3
"""Generate a boot-safe Android font configuration overlay without runtime hooks.

The input document remains the source of truth. LuoShu only redirects explicitly safe named UI
families to pre-generated weighted font files. Locale fallback order, aliases, unnamed script
fallbacks and protected font families are preserved verbatim at the XML-structure level.
"""
from __future__ import annotations

import argparse
import json
import os
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

SAFE_EXACT_FAMILIES = {
    "sans-serif",
    "sans-serif-condensed",
    "roboto",
    "roboto-flex",
    "google-sans",
    "google-sans-text",
    "source-sans-pro",
    "miui",
    "mipro",
    "misans",
    "mi-sans",
    "sys-sans-en",
    "op-sans-en",
}
SAFE_PREFIXES = (
    "sans-serif-",
    "roboto-",
    "google-sans-",
    "miui-",
    "mipro-",
    "misans-",
    "mi-sans-",
    "sys-sans-",
    "op-sans-",
)
PROTECTED_TOKENS = (
    "emoji",
    "symbol",
    "icon",
    "material",
    "dingbat",
    "mono",
    "serif",
    "clock",
    "mitype",
    "math",
    "barcode",
    "qrcode",
)
FONT_SUFFIXES = (".ttf", ".otf", ".ttc")
WEIGHTS = (100, 200, 300, 400, 500, 600, 700, 800, 900)


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def normalize_family(value: str) -> str:
    return value.strip().lower().replace("_", "-")


def is_safe_family(name: str) -> bool:
    normalized = normalize_family(name)
    if not normalized or any(token in normalized for token in PROTECTED_TOKENS):
        return False
    return normalized in SAFE_EXACT_FAMILIES or normalized.startswith(SAFE_PREFIXES)


def is_protected_file(value: str) -> bool:
    filename = os.path.basename(value.strip()).lower()
    return not filename.endswith(FONT_SUFFIXES) or any(token in filename for token in PROTECTED_TOKENS)


def nearest_weight(raw: str | None) -> int:
    try:
        requested = int(raw or "400")
    except ValueError:
        requested = 400
    requested = min(1000, max(1, requested))
    return min(WEIGHTS, key=lambda weight: abs(weight - requested))


def parse_xml(path: Path) -> ET.ElementTree:
    parser = ET.XMLParser(target=ET.TreeBuilder(insert_comments=True))
    return ET.parse(path, parser=parser)


def rewrite_tree(tree: ET.ElementTree, prefix: str) -> dict[str, object]:
    root = tree.getroot()
    changed_families: list[str] = []
    changed_fonts = 0

    for family in root.iter():
        if local_name(family.tag) != "family":
            continue
        family_name = family.attrib.get("name", "")
        if not is_safe_family(family_name):
            continue

        family_changes = 0
        for font in list(family):
            if local_name(font.tag) != "font" or not font.text or is_protected_file(font.text):
                continue
            weight = nearest_weight(font.attrib.get("weight"))
            font.text = f"{prefix}-{weight}.ttf"
            font.attrib.pop("index", None)
            font.attrib.pop("postScriptName", None)
            for child in list(font):
                if local_name(child.tag) == "axis":
                    font.remove(child)
            family_changes += 1

        if family_changes:
            # supportedAxes is valid only when the referenced file is itself variable. LuoShu emits
            # deterministic static weight files so the framework never tries to instantiate axes
            # that are not present in the output font.
            family.attrib.pop("supportedAxes", None)
            changed_fonts += family_changes
            changed_families.append(family_name)

    return {
        "changed": bool(changed_fonts),
        "changed_fonts": changed_fonts,
        "changed_families": sorted(set(changed_families)),
    }


def atomic_write(tree: ET.ElementTree, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    ET.indent(tree, space="    ")
    fd, temporary = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    os.close(fd)
    try:
        tree.write(temporary, encoding="utf-8", xml_declaration=True)
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
    parser.add_argument("--font-prefix", default="LuoShu")
    args = parser.parse_args()

    try:
        tree = parse_xml(args.input)
        report = rewrite_tree(tree, args.font_prefix)
        if report["changed"]:
            atomic_write(tree, args.output)
        else:
            args.output.unlink(missing_ok=True)
        report.update({"status": "ok", "input": str(args.input), "output": str(args.output)})
        print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
        return 0
    except (OSError, ET.ParseError, ValueError) as error:
        args.output.unlink(missing_ok=True)
        print(
            json.dumps(
                {"status": "error", "input": str(args.input), "message": str(error)},
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
