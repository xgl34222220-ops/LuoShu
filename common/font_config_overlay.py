#!/usr/bin/env python3
"""Generate and validate boot-safe Android font configuration overlays.

The device document remains the source of truth. LuoShu only redirects explicitly safe named UI
families to pre-generated static weight files. Locale fallback order, aliases, unnamed script
fallbacks, italic faces and protected font families remain untouched.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

SAFE_EXACT_FAMILIES = {
    "sans", "sans-serif", "sans-serif-condensed", "default", "default-sans",
    "system-ui", "ui-sans-serif", "roboto", "roboto-flex", "roboto-static",
    "google-sans", "google-sans-text", "google-sans-flex", "source-sans",
    "source-sans-pro", "noto-sans", "noto-sans-cjk", "miui", "mipro",
    "misans", "mi-sans", "sysfont", "sys-font", "sys-sans", "sys-sans-en",
    "op-sans", "op-sans-en", "oplus-sans", "oppo-sans", "opposans",
    "coloros-sans", "oneplus-sans", "realme-sans", "vivo-sans",
    "origin-sans", "honor-sans", "harmonyos-sans",
}
SAFE_PREFIXES = (
    "sans-serif-", "roboto-", "google-sans-", "source-sans-", "noto-sans-",
    "miui-", "mipro-", "misans-", "mi-sans-", "sysfont-", "sys-font-",
    "sys-sans-", "op-sans-", "oplus-sans-", "oppo-sans-", "opposans-",
    "coloros-sans-", "oneplus-sans-", "realme-sans-", "vivo-sans-",
    "origin-sans-", "honor-sans-", "harmonyos-sans-",
)
PROTECTED_FAMILY_TOKENS = (
    "emoji", "symbol", "icon", "material", "dingbat", "mono",
    "clock", "mitype", "math", "music", "braille", "barcode", "qrcode",
    "fallback", "legacy",
)
# serif is protected at the file level, but the canonical UI family is named sans-serif.
PROTECTED_FILE_TOKENS = PROTECTED_FAMILY_TOKENS + ("serif",)
FONT_SUFFIXES = (".ttf", ".otf", ".ttc")
WEIGHTS = (100, 200, 300, 400, 500, 600, 700, 800, 900)
MIN_FONT_BYTES = 1024


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def normalize_family(value: str) -> str:
    return value.strip().lower().replace("_", "-")


def is_safe_family(name: str) -> bool:
    normalized = normalize_family(name)
    if not normalized:
        return False
    safe = normalized in SAFE_EXACT_FAMILIES or normalized.startswith(SAFE_PREFIXES)
    return safe and not any(token in normalized for token in PROTECTED_FAMILY_TOKENS)


def is_locale_specific_family(family: ET.Element) -> bool:
    return any(
        family.attrib.get(key)
        for key in ("lang", "variant", "fallbackFor", "fallbackfor")
    )


def is_protected_file(value: str) -> bool:
    filename = os.path.basename(value.strip()).lower()
    return not filename.endswith(FONT_SUFFIXES) or any(
        token in filename for token in PROTECTED_FILE_TOKENS
    )


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
        if is_locale_specific_family(family) or not is_safe_family(family_name):
            continue

        family_changes = 0
        for font in list(family):
            if local_name(font.tag) != "font" or not font.text or is_protected_file(font.text):
                continue
            # Phase one deliberately keeps real italic/oblique faces. Replacing them with an upright
            # file would silently destroy style semantics and can change text measurement.
            if font.attrib.get("style", "normal").lower() in {"italic", "oblique"}:
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
            # supportedAxes is valid only when every referenced face follows the original variable
            # contract. LuoShu emits deterministic static weight files for the rewritten normal faces.
            family.attrib.pop("supportedAxes", None)
            changed_fonts += family_changes
            changed_families.append(family_name)

    return {
        "changed": bool(changed_fonts),
        "changed_fonts": changed_fonts,
        "changed_families": sorted(set(changed_families)),
    }


def generated_references(tree: ET.ElementTree, prefix: str) -> list[str]:
    pattern = re.compile(rf"^{re.escape(prefix)}-(?:100|200|300|400|500|600|700|800|900)\.ttf$")
    references: list[str] = []
    for element in tree.getroot().iter():
        if local_name(element.tag) != "font" or not element.text:
            continue
        filename = element.text.strip()
        if pattern.fullmatch(filename):
            references.append(filename)
    return sorted(set(references))


def validate_generated_references(tree: ET.ElementTree, prefix: str, font_dir: Path) -> int:
    references = generated_references(tree, prefix)
    for filename in references:
        path = font_dir / filename
        if not path.is_file():
            raise ValueError(f"missing generated font: {filename}")
        if path.stat().st_size < MIN_FONT_BYTES:
            raise ValueError(f"generated font is too small: {filename}")
    return len(references)


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
    parser.add_argument("--output", type=Path)
    parser.add_argument("--font-prefix", default="LuoShu")
    parser.add_argument("--font-dir", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    try:
        tree = parse_xml(args.input)
        if args.validate_only:
            references = 0
            if args.font_dir is not None:
                references = validate_generated_references(tree, args.font_prefix, args.font_dir)
            print(
                json.dumps(
                    {"status": "ok", "input": str(args.input), "generated_references": references},
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )
            return 0

        if args.output is None:
            raise ValueError("--output is required unless --validate-only is used")
        report = rewrite_tree(tree, args.font_prefix)
        references = 0
        if args.font_dir is not None:
            references = validate_generated_references(tree, args.font_prefix, args.font_dir)
        if report["changed"]:
            atomic_write(tree, args.output)
        else:
            args.output.unlink(missing_ok=True)
        report.update(
            {
                "status": "ok",
                "input": str(args.input),
                "output": str(args.output),
                "generated_references": references,
            }
        )
        print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
        return 0
    except (OSError, ET.ParseError, ValueError) as error:
        if args.output is not None:
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
