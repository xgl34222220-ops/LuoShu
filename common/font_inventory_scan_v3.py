#!/usr/bin/env python3
"""Extended stock-font inventory scanner.

Revision 3 keeps replaceable slots restricted to the partitions supported by the
runtime, while broadening diagnostics to OEM/alias roots and keeping theme fonts
separate from immutable stock files.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Iterable

import font_inventory as base
import font_inventory_scan as v2

SCANNER_REVISION = 3
PRIMARY_FONT_SPECS = (
    ("system", Path("/system/fonts"), "system_fonts", (Path("/system/font"),)),
    ("system_ext", Path("/system_ext/fonts"), "system_ext_fonts", (Path("/system/system_ext/fonts"),)),
    ("product", Path("/product/fonts"), "product_fonts", (Path("/system/product/fonts"),)),
    ("my_product", Path("/my_product/fonts"), "my_product_fonts", (Path("/system/my_product/fonts"),)),
    ("vendor", Path("/vendor/fonts"), "vendor_fonts", (Path("/system/vendor/fonts"),)),
)
PRIMARY_ETC_SPECS = (
    ("system", Path("/system/etc"), "system_etc", ()),
    ("system_ext", Path("/system_ext/etc"), "system_ext_etc", (Path("/system/system_ext/etc"),)),
    ("product", Path("/product/etc"), "product_etc", (Path("/system/product/etc"),)),
    ("my_product", Path("/my_product/etc"), "my_product_etc", (Path("/system/my_product/etc"),)),
    ("vendor", Path("/vendor/etc"), "vendor_etc", (Path("/system/vendor/etc"),)),
)
AUX_FONT_SPECS = (
    ("odm", Path("/odm/fonts"), "odm_fonts"),
    ("oem", Path("/oem/fonts"), "oem_fonts"),
    ("my_region", Path("/my_region/fonts"), "my_region_fonts"),
    ("hw_product", Path("/hw_product/fonts"), "hw_product_fonts"),
)
AUX_ETC_SPECS = (
    ("odm", Path("/odm/etc"), "odm_etc"),
    ("oem", Path("/oem/etc"), "oem_etc"),
    ("my_region", Path("/my_region/etc"), "my_region_etc"),
    ("hw_product", Path("/hw_product/etc"), "hw_product_etc"),
)
THEME_FONT_ROOTS = (
    Path("/data/system/theme/fonts"),
    Path("/data/system/theme_magic/fonts"),
    Path("/data/themes"),
    Path("/data/theme/fonts"),
    Path("/data/fonts/files"),
    Path("/data/bbkcore/theme"),
    Path("/data/oplus/uxres/theme"),
    Path("/data/skin/fonts"),
)
ROM_FONT_MARKERS = {
    "hyperos": ("MiSansVF.ttf", "MiSansVF_Overlay.ttf", "MiLanProVF.ttf", "MiSans-Regular.ttf"),
    "coloros": ("SysSans-Hans-Regular.ttf", "SysFont-Hans-Regular.ttf", "OPlusSans3.0.ttf", "ColorOSUI-Regular.ttf"),
    "originos": ("VivoFont.ttf", "DroidSansFallbackBBK.ttf"),
    "oneui": ("SamsungOneUI-Regular.ttf", "SECRobotoLight-Regular.ttf"),
    "flyme": ("FlymeSans-Regular.ttf",),
    "harmonyos": ("HarmonyOS_Sans_SC_Regular.ttf", "HwChinese-Medium.ttf"),
    "magicos": ("HONORSansVF.ttf",),
    "aosp": ("Roboto-Regular.ttf", "NotoSansCJK-Regular.ttc", "NotoSansSC-VF.otf"),
}


def _resolve_actual(logical: Path, explicit: Path | None, aliases: Iterable[Path], overlay_risk: bool) -> Path:
    if explicit is not None:
        return explicit
    candidates = (logical, *tuple(aliases))
    if overlay_risk:
        for candidate in candidates:
            for prefix in base.MIRROR_PREFIXES:
                mirrored = prefix / candidate.relative_to("/")
                if mirrored.is_dir():
                    return mirrored
        raise base.InventoryError(f"旧版字体覆盖仍在活动，无法安全读取原厂目录：{logical}")
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return logical


def _resolve_primary_font_roots(args: Any, overlay_risk: bool) -> list[base.FontRoot]:
    return [
        base.FontRoot(partition, logical, _resolve_actual(logical, getattr(args, argument), aliases, overlay_risk))
        for partition, logical, argument, aliases in PRIMARY_FONT_SPECS
    ]


def _resolve_aux_font_roots(args: Any, overlay_risk: bool) -> list[base.FontRoot]:
    del overlay_risk
    return [
        base.FontRoot(partition, logical, _resolve_actual(logical, getattr(args, argument), (), False))
        for partition, logical, argument in AUX_FONT_SPECS
    ]


def _resolve_etc_roots(args: Any, overlay_risk: bool) -> list[tuple[str, Path, Path]]:
    roots: list[tuple[str, Path, Path]] = []
    for partition, logical, argument, aliases in PRIMARY_ETC_SPECS:
        roots.append((partition, logical, _resolve_actual(logical, getattr(args, argument), aliases, overlay_risk)))
    for partition, logical, argument in AUX_ETC_SPECS:
        roots.append((partition, logical, _resolve_actual(logical, getattr(args, argument), (), False)))
    return roots


def _font_identity(path: Path) -> tuple[str, int, int] | tuple[str, str]:
    try:
        stat = path.stat()
        return ("inode", int(stat.st_dev), int(stat.st_ino))
    except OSError:
        try:
            return ("path", str(path.resolve()))
        except OSError:
            return ("path", str(path))


def _stock_file_counts(font_roots: Iterable[base.FontRoot]) -> tuple[int, int, dict[str, int], dict[str, int], set[str]]:
    path_total = 0
    unique_total = 0
    path_counts: dict[str, int] = {}
    unique_counts: dict[str, int] = {}
    identities: set[tuple[Any, ...]] = set()
    names: set[str] = set()
    for root in font_roots:
        partition_paths = 0
        partition_unique = 0
        if root.actual.is_dir():
            for path in root.actual.rglob("*"):
                if not path.is_file() or path.suffix.lower() not in base.FONT_EXTENSIONS:
                    continue
                partition_paths += 1
                path_total += 1
                names.add(path.name)
                identity = _font_identity(path)
                if identity in identities:
                    continue
                identities.add(identity)
                partition_unique += 1
                unique_total += 1
        path_counts[root.partition] = partition_paths
        unique_counts[root.partition] = partition_unique
    return path_total, unique_total, path_counts, unique_counts, names


def _contains_font_capped(root: Path, limit: int = 4096) -> bool:
    seen = 0
    try:
        for _directory, _subdirs, files in os.walk(root):
            for name in files:
                seen += 1
                if Path(name).suffix.lower() in base.FONT_EXTENSIONS:
                    return True
                if seen >= limit:
                    return False
    except OSError:
        return False
    return False


def _theme_override_roots() -> list[str]:
    found: list[str] = []
    for root in THEME_FONT_ROOTS:
        if root.is_dir() and _contains_font_capped(root):
            found.append(str(root))
    return found


def _font_mount_targets() -> list[str]:
    targets: set[str] = set()
    try:
        lines = Path("/proc/mounts").read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    for line in lines:
        fields = line.split()
        if len(fields) < 2:
            continue
        target = fields[1].replace("\\040", " ")
        lowered = target.lower()
        if "/fonts" in lowered or lowered.startswith("/data/fonts"):
            targets.add(target)
    return sorted(targets)


def _rom_markers(names: set[str]) -> dict[str, list[str]]:
    lowered = {name.lower(): name for name in names}
    result: dict[str, list[str]] = {}
    for rom, markers in ROM_FONT_MARKERS.items():
        matches = [lowered[marker.lower()] for marker in markers if marker.lower() in lowered]
        if matches:
            result[rom] = matches
    return result


def _can_reuse(existing: dict[str, Any], build_key: str) -> bool:
    try:
        base.validate_inventory(existing, build_key)
    except base.InventoryError:
        return False
    summary = existing.get("scanSummary")
    return (
        int(existing.get("scannerRevision", 0) or 0) == SCANNER_REVISION
        and isinstance(summary, dict)
        and "stockFontUniqueFileCount" in summary
        and "themeOverrideRoots" in summary
    )


def scan(args: Any) -> int:
    output: Path = args.output
    build_key, fingerprint, display_id = base.current_build_key(args.build_key)
    existing = base._load_json(output)
    if not args.force and existing is not None and _can_reuse(existing, build_key):
        summary = existing["scanSummary"]
        print(json.dumps({
            "status": "reused",
            "buildKey": build_key,
            "slotCount": len(existing["slots"]),
            "stockFontFileCount": int(summary.get("stockFontFileCount", 0)),
            "stockFontUniqueFileCount": int(summary.get("stockFontUniqueFileCount", 0)),
            "xmlSlotCount": int(summary.get("xmlUiFileCount", 0)),
            "heuristicSlotCount": int(summary.get("heuristicUiFileCount", 0)),
            "themeOverrideCount": len(summary.get("themeOverrideRoots", [])),
            "romKind": existing.get("romKind", "generic"),
        }, ensure_ascii=False))
        return 0
    if existing is not None:
        try:
            base.validate_inventory(existing, build_key)
        except base.InventoryError:
            output.unlink(missing_ok=True)

    risk = base._overlay_risk(args.overlay_module)
    primary_roots = _resolve_primary_font_roots(args, risk)
    auxiliary_roots = _resolve_aux_font_roots(args, risk)
    etc_roots = _resolve_etc_roots(args, risk)
    xml_sources = v2._discover_xml_sources(etc_roots)

    base._is_ui_family = v2._is_ui_family
    families, slots = v2._parse_partition_xml(xml_sources, primary_roots)
    base._add_heuristic_slots(slots, primary_roots, args.font_check)
    base._populate_metrics(slots)
    main_path, main_entry, rom = base._pick_main_slot(slots, families)

    path_total, unique_total, path_counts, unique_counts, names = _stock_file_counts((*primary_roots, *auxiliary_roots))
    theme_roots = _theme_override_roots()
    mount_targets = _font_mount_targets()
    scan_summary = v2._summary(slots, path_total, path_counts, len(xml_sources), v2._count_xml_ui_faces(xml_sources))
    scan_summary.update({
        "stockFontUniqueFileCount": unique_total,
        "partitionUniqueFontFileCounts": unique_counts,
        "themeOverrideRoots": theme_roots,
        "fontMountTargets": mount_targets,
        "fontSignatures": _rom_markers(names),
        "stockCountSemantics": "font paths from canonical-or-alias partition roots; theme fonts excluded",
    })
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
            for root in primary_roots if root.actual.is_dir()
        ],
        "auxiliaryRoots": [
            {"partition": root.partition, "logical": str(root.logical), "actual": str(root.actual)}
            for root in auxiliary_roots if root.actual.is_dir()
        ],
        "etcRoots": [
            {"partition": partition, "logical": str(logical), "actual": str(actual)}
            for partition, logical, actual in etc_roots if actual.is_dir()
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
    print(json.dumps({
        "status": "ok",
        "buildKey": build_key,
        "slotCount": len(slots),
        "stockFontFileCount": path_total,
        "stockFontUniqueFileCount": unique_total,
        "xmlSlotCount": scan_summary["xmlUiFileCount"],
        "heuristicSlotCount": scan_summary["heuristicUiFileCount"],
        "xmlSourceCount": scan_summary["xmlSourceCount"],
        "themeOverrideCount": len(theme_roots),
        "fontMountCount": len(mount_targets),
        "mainSlot": main_entry["slotName"],
        "romKind": rom,
    }, ensure_ascii=False))
    return 0


def build_parser() -> Any:
    parser = v2.build_parser()
    parser.add_argument("--odm-fonts", type=Path)
    parser.add_argument("--oem-fonts", type=Path)
    parser.add_argument("--my-region-fonts", type=Path)
    parser.add_argument("--hw-product-fonts", type=Path)
    parser.add_argument("--odm-etc", type=Path)
    parser.add_argument("--oem-etc", type=Path)
    parser.add_argument("--my-region-etc", type=Path)
    parser.add_argument("--hw-product-etc", type=Path)
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
        print(json.dumps({"status": "error", "message": str(error) or error.__class__.__name__}, ensure_ascii=False), file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
