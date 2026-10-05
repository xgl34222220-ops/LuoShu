#!/usr/bin/env python3
"""Generate and validate boot-safe Android font configuration overlays.

The device document remains the source of truth. LuoShu redirects named UI families to
balanced static weights and redirects named monospace families to a dedicated fixed-width
derivative. Locale fallbacks, emoji, icons, symbols, serif faces and true italic faces
remain untouched.
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
    "oplus-os-ui", "oplusosui", "coloros-sans", "oneplus-sans", "realme-sans",
    "vivo-sans", "vivosans", "vivo-sans-vf", "origin", "originos", "origin-sans",
    "originos-sans", "iqoo-sans", "iqoosans", "flyme", "flyme-sans", "flyme-ui",
    "flymesans", "flymefont", "meizu", "meizu-sans", "meizusans", "mflyme",
    "mflyme-sans", "honor-sans", "harmonyos-sans",
}
SAFE_PREFIXES = (
    "sans-serif-", "roboto-", "google-sans-", "source-sans-", "noto-sans-",
    "miui-", "mipro-", "misans-", "mi-sans-", "sysfont-", "sys-font-",
    "sys-sans-", "op-sans-", "oplus-sans-", "oppo-sans-", "opposans-",
    "oplus-os-ui-", "oplusosui-", "coloros-sans-", "oneplus-sans-", "realme-sans-",
    "vivo-sans-", "vivosans-", "origin-sans-", "originos-sans-", "iqoo-sans-",
    "iqoosans-", "flyme-sans-", "flymesans-", "flymefont-", "meizu-sans-",
    "meizusans-", "mflyme-", "honor-sans-", "harmonyos-sans-",
)
MONO_EXACT_FAMILIES = {
    "monospace", "sans-serif-monospace", "ui-monospace", "roboto-mono",
    "serif-monospace", "noto-serif-mono", "noto-mono", "noto-sans-mono",
    "droid-sans-mono", "courier", "courier-new", "monaco",
}
MONO_PREFIXES = (
    "monospace-", "sans-serif-monospace-", "serif-monospace-", "ui-monospace-",
    "roboto-mono-", "noto-mono-", "noto-sans-mono-", "noto-serif-mono-",
    "droid-sans-mono-", "courier-", "monaco-",
)
PROTECTED_COMMON_TOKENS = (
    "emoji", "symbol", "icon", "material", "dingbat", "clock", "mitype",
    "math", "music", "braille", "barcode", "qrcode", "fallback", "legacy",
)
PROTECTED_UI_FILE_TOKENS = PROTECTED_COMMON_TOKENS + ("mono", "serif")
# A named monospace family is an explicit Android text role. Its stock file may legitimately be
# called NotoSerifMono/CutiveMono, so filename words such as ``serif`` and ``mono`` cannot be used
# to reject it after the family graph has already classified the role.
PROTECTED_MONO_FILE_TOKENS = PROTECTED_COMMON_TOKENS
# `sans` as a whole word anywhere in the family name: sans-serif, misans, hihonor-sans,
# oneui-sans-condensed, vivo-sans-vf ... but not "sansa" or an unrelated substring.
SANS_FAMILY_PATTERN = re.compile(r"(?:^|-)(?:[a-z0-9]*sans)(?:$|-)")
# A serif family must keep its own face. AOSP's sans-serif and ui-sans-serif are UI families
# despite carrying "serif" in the name; vendor serif faces such as misans-serif stay protected.
SERIF_FAMILY_PATTERN = re.compile(r"(?:^|-)serif(?:$|-)")
UI_SANS_SERIF_FAMILIES = ("sans-serif", "ui-sans-serif")
FONT_SUFFIXES = (".ttf", ".otf", ".ttc")
WEIGHTS = (100, 200, 300, 400, 500, 600, 700, 800, 900)
MIN_FONT_BYTES = 1024


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def normalize_family(value: str) -> str:
    return re.sub(r"[\s_-]+", "-", value.strip().lower()).strip("-")


def is_safe_mono_family(name: str) -> bool:
    normalized = normalize_family(name)
    return bool(normalized) and (normalized in MONO_EXACT_FAMILIES or normalized.startswith(MONO_PREFIXES))


def looks_like_sans_family(normalized: str) -> bool:
    """Recognise a UI text family by shape rather than by vendor name.

    A curated list can only ever name the ROMs that existed when it was written, so every OEM that
    calls its UI family something new escapes the overlay and silently keeps the stock font. Any
    family whose name identifies it as a sans / UI text family therefore qualifies, while decorative
    families keep their own names and are left alone.
    """
    if SANS_FAMILY_PATTERN.search(normalized):
        return True
    return normalized.endswith(("-ui-font", "-os-ui", "-uifont"))


def is_safe_family(name: str) -> bool:
    normalized = normalize_family(name)
    if not normalized or is_safe_mono_family(normalized):
        return False
    if any(token in normalized for token in PROTECTED_COMMON_TOKENS):
        return False
    if SERIF_FAMILY_PATTERN.search(normalized) and not (
        normalized in UI_SANS_SERIF_FAMILIES
        or any(normalized.startswith(name + "-") for name in UI_SANS_SERIF_FAMILIES)
    ):
        return False
    return (
        normalized in SAFE_EXACT_FAMILIES
        or normalized.startswith(SAFE_PREFIXES)
        or looks_like_sans_family(normalized)
    )


def is_locale_specific_family(family: ET.Element) -> bool:
    return any(family.attrib.get(key) for key in ("lang", "variant", "fallbackFor", "fallbackfor"))


def effective_family_name(
    family: ET.Element,
    parents: dict[ET.Element, ET.Element],
) -> str:
    """Return the Android named-family role for ``family``.

    Android 14+ product customisations may use ``<family-list name=\"…\">`` with anonymous
    ``<family>`` children. Looking only at ``family.attrib['name']`` leaves those OEM overrides on
    the ROM font even though Android resolves them as a named family. A child's own name still wins.
    """
    own = family.attrib.get("name", "")
    if own:
        return own
    parent = parents.get(family)
    if parent is not None and local_name(parent.tag) == "family-list":
        return parent.attrib.get("name", "")
    return ""


def is_protected_file(value: str, mono: bool = False) -> bool:
    filename = os.path.basename(value.strip()).lower()
    tokens = PROTECTED_MONO_FILE_TOKENS if mono else PROTECTED_UI_FILE_TOKENS
    return not filename.endswith(FONT_SUFFIXES) or any(token in filename for token in tokens)


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


def rewrite_tree(tree: ET.ElementTree, prefix: str, mono_prefix: str = "LuoShuMono") -> dict[str, object]:
    root = tree.getroot()
    parents = {child: parent for parent in root.iter() for child in list(parent)}
    changed_families: list[str] = []
    changed_mono_families: list[str] = []
    changed_fonts = 0

    for family in root.iter():
        if local_name(family.tag) != "family":
            continue
        family_name = effective_family_name(family, parents)
        if is_locale_specific_family(family):
            continue
        parent = parents.get(family)
        if parent is not None and local_name(parent.tag) == "family-list" and is_locale_specific_family(parent):
            continue
        mono = is_safe_mono_family(family_name)
        if not mono and not is_safe_family(family_name):
            continue
        selected_prefix = mono_prefix if mono else prefix

        family_changes = 0
        for font in list(family):
            if local_name(font.tag) != "font" or not font.text or is_protected_file(font.text, mono=mono):
                continue
            if font.attrib.get("style", "normal").lower() in {"italic", "oblique"}:
                continue
            weight = nearest_weight(font.attrib.get("weight"))
            font.text = f"{selected_prefix}-{weight}.ttf"
            font.attrib.pop("index", None)
            font.attrib.pop("postScriptName", None)
            for child in list(font):
                if local_name(child.tag) == "axis":
                    font.remove(child)
            family_changes += 1

        if family_changes:
            family.attrib.pop("supportedAxes", None)
            changed_fonts += family_changes
            (changed_mono_families if mono else changed_families).append(family_name)

    return {
        "changed": bool(changed_fonts),
        "changed_fonts": changed_fonts,
        "changed_families": sorted(set(changed_families)),
        "changed_mono_families": sorted(set(changed_mono_families)),
    }


def generated_references(tree: ET.ElementTree, prefixes: tuple[str, ...]) -> list[str]:
    prefix_pattern = "|".join(re.escape(prefix) for prefix in prefixes)
    pattern = re.compile(rf"^(?:{prefix_pattern})-(?:100|200|300|400|500|600|700|800|900)\.ttf$")
    references: list[str] = []
    for element in tree.getroot().iter():
        if local_name(element.tag) != "font" or not element.text:
            continue
        filename = element.text.strip()
        if pattern.fullmatch(filename):
            references.append(filename)
    return sorted(set(references))


def validate_generated_references(tree: ET.ElementTree, prefixes: tuple[str, ...], font_dir: Path) -> int:
    references = generated_references(tree, prefixes)
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


def run_batch(job_file: Path, prefixes: tuple[str, ...]) -> int:
    """Process many documents in one interpreter.

    A switch touches every font configuration document the ROM ships, and each one previously cost
    its own interpreter start: capture-validate, generate, validate-generated. On a phone the
    embedded CPython takes far longer to start than this script takes to run, so the switch was
    dominated by process startup and grew linearly with the number of documents on the device.
    One process handles the whole list instead.

    Job lines are tab separated so that paths containing '|' or spaces stay intact:
        validate<TAB>input<TAB>font_dir
        generate<TAB>input<TAB>output<TAB>font_dir
    Each result line is: op<TAB>input<TAB>status<TAB>changed<TAB>references<TAB>message
    """
    failures = 0
    for raw in job_file.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip("\n")
        if not line.strip():
            continue
        fields = line.split("\t")
        op = fields[0]
        source = Path(fields[1]) if len(fields) > 1 else None
        changed = "0"
        references = 0
        try:
            if source is None:
                raise ValueError("missing input path")
            if op == "validate":
                font_dir = Path(fields[2]) if len(fields) > 2 and fields[2] else None
                tree = parse_xml(source)
                references = validate_generated_references(tree, prefixes, font_dir) if font_dir else 0
            elif op == "generate":
                if len(fields) < 3 or not fields[2]:
                    raise ValueError("missing output path")
                output = Path(fields[2])
                font_dir = Path(fields[3]) if len(fields) > 3 and fields[3] else None
                tree = parse_xml(source)
                report = rewrite_tree(tree, prefixes[0], prefixes[1])
                references = validate_generated_references(tree, prefixes, font_dir) if font_dir else 0
                if report["changed"]:
                    atomic_write(tree, output)
                else:
                    output.unlink(missing_ok=True)
                changed = "1" if report["changed"] else "0"
            else:
                raise ValueError(f"unknown batch op: {op}")
        except (OSError, ET.ParseError, ValueError, IndexError) as error:
            failures += 1
            message = str(error) or error.__class__.__name__
            print(f"{op}\t{source or ''}\terror\t0\t0\t{message}".replace("\n", " "))
            continue
        print(f"{op}\t{source}\tok\t{changed}\t{references}\t")
    # A per-item failure is reported on its own line; the exit code only reports whether the batch
    # itself could be read, so one unusable ROM document cannot discard the others.
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path)
    parser.add_argument("--batch", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--font-prefix", default="LuoShu")
    parser.add_argument("--mono-font-prefix", default="LuoShuMono")
    parser.add_argument("--font-dir", type=Path)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    prefixes = (args.font_prefix, args.mono_font_prefix)

    if args.batch is not None:
        try:
            return run_batch(args.batch, prefixes)
        except OSError as error:
            print(json.dumps({"status": "error", "message": str(error)}, ensure_ascii=False, separators=(",", ":")))
            return 2
    if args.input is None:
        parser.error("--input is required unless --batch is used")

    try:
        tree = parse_xml(args.input)
        if args.validate_only:
            references = validate_generated_references(tree, prefixes, args.font_dir) if args.font_dir else 0
            print(json.dumps({"status": "ok", "input": str(args.input), "generated_references": references}, ensure_ascii=False, separators=(",", ":")))
            return 0
        if args.output is None:
            raise ValueError("--output is required unless --validate-only is used")
        report = rewrite_tree(tree, args.font_prefix, args.mono_font_prefix)
        references = validate_generated_references(tree, prefixes, args.font_dir) if args.font_dir else 0
        if report["changed"]:
            atomic_write(tree, args.output)
        else:
            args.output.unlink(missing_ok=True)
        report.update({"status": "ok", "input": str(args.input), "output": str(args.output), "generated_references": references})
        print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
        return 0
    except (OSError, ET.ParseError, ValueError) as error:
        if args.output is not None:
            args.output.unlink(missing_ok=True)
        print(json.dumps({"status": "error", "input": str(args.input), "message": str(error)}, ensure_ascii=False, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
