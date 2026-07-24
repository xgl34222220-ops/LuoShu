#!/usr/bin/env python3
"""Partition-aware stock font inventory scanner.

This is the v2 discovery entry point. It keeps the v1 JSON schema consumed by the
runtime, but fixes UI-family classification, reads font XML from every supported
partition, and reports total stock files separately from replaceable UI slots.
"""
from __future__ import annotations

import json
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Iterable

import font_inventory as base

SCANNER_REVISION = 2
ETC_ROOTS = (
    ("system", Path("/system/etc"), "system_etc"),
    ("system_ext", Path("/system_ext/etc"), "system_ext_etc"),
    ("product", Path("/product/etc"), "product_etc"),
    ("my_product", Path("/my_product/etc"), "my_product_etc"),
    ("vendor", Path("/vendor/etc"), "vendor_etc"),
)
XML_PATTERNS = (
    "fonts.xml",
    "font_fallback.xml",
    "fonts_customization.xml",
    "fonts*.xml",
    "font_fallback*.xml",
)


def _is_ui_family(name: str) -> bool:
    """Classify UI families without rejecting ``sans-serif`` because it contains ``serif``."""
    lowered = name.strip().lower().replace("_", "-")
    if not lowered:
        return False
    if lowered == "sans-serif":
        return True
    if lowered.startswith("sans-serif-"):
        suffix = lowered.removeprefix("sans-serif-")
        parts = [part for part in suffix.split("-") if part]
        return bool(parts) and all(part in base.SANS_SERIF_UI_SUFFIX_TOKENS for part in parts)

    tokens = {token for token in re.split(r"[^a-z0-9]+", lowered) if token}
    if tokens.intersection({"serif", "mono", "monospace", "emoji", "symbol", "icon", "math", "music"}):
        return False
    return any(
        lowered == prefix or lowered.startswith(prefix + "-")
        for prefix in base.UI_FAMILY_PREFIXES
        if prefix != "sans-serif"
    )


def _resolve_etc_roots(args: Any, overlay_risk: bool) -> list[tuple[str, Path, Path]]:
    roots: list[tuple[str, Path, Path]] = []
    for partition, logical, argument_name in ETC_ROOTS:
        explicit = getattr(args, argument_name, None)
        actual = base._pick_actual_root(logical, explicit, overlay_risk)
        roots.append((partition, logical, actual))
    return roots


def _discover_xml_sources(etc_roots: Iterable[tuple[str, Path, Path]]) -> list[tuple[str, Path, Path]]:
    discovered: dict[str, tuple[str, Path, Path]] = {}
    for partition, logical_root, actual_root in etc_roots:
        if not actual_root.is_dir():
            continue
        for pattern in XML_PATTERNS:
            for actual in actual_root.glob(pattern):
                if not actual.is_file():
                    continue
                logical = logical_root / actual.relative_to(actual_root)
                discovered[str(logical)] = (partition, logical, actual)
    return [discovered[key] for key in sorted(discovered)]


def _merge_families(target: dict[str, list[str]], source: dict[str, list[str]]) -> None:
    for family, paths in source.items():
        bucket = target.setdefault(family, [])
        for path in paths:
            if path not in bucket:
                bucket.append(path)


def _merge_slots(target: dict[str, dict[str, Any]], source: dict[str, dict[str, Any]], xml_paths: list[str]) -> None:
    for logical, candidate in source.items():
        if logical not in target:
            target[logical] = {**candidate, "sourceXmls": list(xml_paths)}
            continue
        current = target[logical]
        for family in candidate.get("families", []):
            if family not in current.setdefault("families", []):
                current["families"].append(family)
        for xml_path in xml_paths:
            if xml_path not in current.setdefault("sourceXmls", []):
                current["sourceXmls"].append(xml_path)
        if current.get("source") != "xml" and candidate.get("source") == "xml":
            preserved_families = list(current.get("families", []))
            preserved_sources = list(current.get("sourceXmls", []))
            current.clear()
            current.update(candidate)
            current["families"] = preserved_families
            current["sourceXmls"] = preserved_sources


def _parse_partition_xml(
    xml_sources: list[tuple[str, Path, Path]],
    font_roots: list[base.FontRoot],
) -> tuple[dict[str, list[str]], dict[str, dict[str, Any]]]:
    families: dict[str, list[str]] = {}
    slots: dict[str, dict[str, Any]] = {}
    for partition, logical_xml, actual_xml in xml_sources:
        preferred = [root for root in font_roots if root.partition == partition]
        ordered_roots = preferred + [root for root in font_roots if root.partition != partition]
        local_families, local_slots = base._parse_xml_mappings([actual_xml], ordered_roots)
        _merge_families(families, local_families)
        _merge_slots(slots, local_slots, [str(logical_xml)])
    return families, slots


def _count_xml_ui_faces(xml_sources: Iterable[tuple[str, Path, Path]]) -> int:
    faces: set[tuple[str, str, str, str]] = set()
    for _partition, logical_xml, actual_xml in xml_sources:
        try:
            root = ET.parse(actual_xml).getroot()
        except (OSError, ET.ParseError):
            continue
        for family in root.iter():
            if base._local_name(family.tag) != "family":
                continue
            family_name = (family.get("name") or "").strip()
            family_language = (family.get("lang") or "").strip()
            if family_language or not _is_ui_family(family_name):
                continue
            for font in family:
                if base._local_name(font.tag) != "font":
                    continue
                raw_name = (font.text or "").strip()
                if not raw_name:
                    continue
                faces.add(
                    (
                        str(logical_xml),
                        raw_name,
                        font.get("index") or "0",
                        (font.get("weight") or "400") + ":" + (font.get("style") or "normal"),
                    )
                )
    return len(faces)


def _stock_file_counts(font_roots: Iterable[base.FontRoot]) -> tuple[int, dict[str, int]]:
    total = 0
    partitions: dict[str, int] = {}
    for root in font_roots:
        count = 0
        if root.actual.is_dir():
            for path in root.actual.rglob("*"):
                if path.is_file() and path.suffix.lower() in base.FONT_EXTENSIONS:
                    count += 1
        partitions[root.partition] = count
        total += count
    return total, partitions


def _slot_partition_counts(slots: dict[str, dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for entry in slots.values():
        partition = str(entry.get("partition", "unknown"))
        counts[partition] = counts.get(partition, 0) + 1
    return counts


def _summary(slots: dict[str, dict[str, Any]], stock_total: int, stock_parts: dict[str, int], xml_source_count: int, xml_face_count: int) -> dict[str, Any]:
    xml_slots = sum(1 for entry in slots.values() if entry.get("source") == "xml")
    heuristic_slots = len(slots) - xml_slots
    return {
        "stockFontFileCount": stock_total,
        "partitionFontFileCounts": stock_parts,
        "uiFileCount": len(slots),
        "uiXmlFaceCount": xml_face_count,
        "xmlUiFileCount": xml_slots,
        "heuristicUiFileCount": heuristic_slots,
        "xmlSourceCount": xml_source_count,
        "partitionUiFileCounts": _slot_partition_counts(slots),
    }


def _can_reuse(existing: dict[str, Any], build_key: str) -> bool:
    try:
        base.validate_inventory(existing, build_key)
    except base.InventoryError:
        return False
    return int(existing.get("scannerRevision", 0) or 0) == SCANNER_REVISION and isinstance(existing.get("scanSummary"), dict)


def scan(args: Any) -> int:
    output: Path = args.output
    build_key, fingerprint, display_id = base.current_build_key(args.build_key)
    existing = base._load_json(output)
    if not args.force and existing is not None and _can_reuse(existing, build_key):
        summary = existing["scanSummary"]
        print(
            json.dumps(
                {
                    "status": "reused",
                    "buildKey": build_key,
                    "slotCount": len(existing["slots"]),
                    "stockFontFileCount": int(summary.get("stockFontFileCount", 0)),
                    "xmlSlotCount": int(summary.get("xmlUiFileCount", 0)),
                    "heuristicSlotCount": int(summary.get("heuristicUiFileCount", 0)),
                    "romKind": existing.get("romKind", "generic"),
                },
                ensure_ascii=False,
            )
        )
        return 0

    if existing is not None:
        try:
            base.validate_inventory(existing, build_key)
        except base.InventoryError:
            output.unlink(missing_ok=True)

    risk = base._overlay_risk(args.overlay_module)
    font_roots, _legacy_system_etc = base._resolve_roots(args, risk)
    etc_roots = _resolve_etc_roots(args, risk)
    xml_sources = _discover_xml_sources(etc_roots)

    # Patch the v1 helper for this process. The old substring check rejected the exact
    # family name "sans-serif" because it contains the word "serif".
    base._is_ui_family = _is_ui_family
    families, slots = _parse_partition_xml(xml_sources, font_roots)
    base._add_heuristic_slots(slots, font_roots, args.font_check)
    base._populate_metrics(slots)
    main_path, main_entry, rom = base._pick_main_slot(slots, families)

    stock_total, stock_parts = _stock_file_counts(font_roots)
    scan_summary = _summary(slots, stock_total, stock_parts, len(xml_sources), _count_xml_ui_faces(xml_sources))
    inventory = {
        "schema": base.SCHEMA,
        "inventoryRevision": base.INVENTORY_REVISION,
        "scannerRevision": SCANNER_REVISION,
        "state": "ready",
        "buildKey": build_key,
        "buildFingerprint": fingerprint,
        "buildDisplayId": display_id,
        "generatedAt": int(time.time()),
        "romKind": rom,
        "sourceRoots": [
            {"partition": root.partition, "logical": str(root.logical), "actual": str(root.actual)}
            for root in font_roots
            if root.actual.is_dir()
        ],
        "etcRoots": [
            {"partition": partition, "logical": str(logical), "actual": str(actual)}
            for partition, logical, actual in etc_roots
            if actual.is_dir()
        ],
        "xmlSources": [str(logical) for _partition, logical, _actual in xml_sources],
        "families": {name: paths for name, paths in sorted(families.items()) if name and paths},
        "slots": {logical: slots[logical] for logical in sorted(slots)},
        "slotCount": len(slots),
        "scanSummary": scan_summary,
        "mainSlotPath": main_path,
        "mainSlot": {**main_entry, "path": main_path},
    }
    base.validate_inventory(inventory, build_key)
    base._atomic_write(output, inventory)
    print(
        json.dumps(
            {
                "status": "ok",
                "buildKey": build_key,
                "slotCount": len(slots),
                "stockFontFileCount": stock_total,
                "xmlSlotCount": scan_summary["xmlUiFileCount"],
                "heuristicSlotCount": scan_summary["heuristicUiFileCount"],
                "xmlSourceCount": scan_summary["xmlSourceCount"],
                "mainSlot": main_entry["slotName"],
                "romKind": rom,
            },
            ensure_ascii=False,
        )
    )
    return 0


def build_parser() -> Any:
    parser = base.build_parser()
    parser.add_argument("--system-ext-etc", type=Path)
    parser.add_argument("--product-etc", type=Path)
    parser.add_argument("--my-product-etc", type=Path)
    parser.add_argument("--vendor-etc", type=Path)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.list:
            return base.list_slots(args)
        if args.validate:
            return base.validate_command(args)
        return scan(args)
    except Exception as error:
        print(json.dumps({"status": "error", "message": str(error) or error.__class__.__name__}, ensure_ascii=False), file=base.os.sys.stderr)
        return 2


if __name__ == "__main__":
    from font_inventory_scan_v3 import main as v3_main

    raise SystemExit(v3_main())
